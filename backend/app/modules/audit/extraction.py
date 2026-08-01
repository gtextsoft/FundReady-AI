"""Stage 1 of the audit pipeline: documents to Startup Profile fields (T2.4).

Layer: **service** (ARCHITECTURE.md section 3). Takes bytes, returns values. It
does not touch the database, object storage, or the network beyond the one model
call, which is what makes it testable without R2 (T1.5 has never stored a byte).
`audit.pipeline` owns fetching the bytes and persisting the result.

**Two ways in, chosen per format.** PDFs and images go to the API as native
`document`/`image` blocks rather than through a text extractor, because a deck
is usually a design artefact: a text extractor returns the speaker notes and
misses the chart that carries the number, and a photographed cap table has no
text layer at all. The Office formats the upload allowlist accepts cannot be
sent natively, so those are parsed to text here.

**On fencing.** Inlined text is fenced with `ai.guards` as everywhere else.
Native `document` blocks are not, and do not need to be: the block boundary is
structural rather than lexical, so content inside it cannot forge its way into
instruction position the way a string concatenated into a prompt can. That is a
stronger boundary than the fence, not a weaker one -- but it is only true
because the bytes go over as a block. Inlining a PDF's text without fencing it
would reopen exactly the hole `guards` exists to close.

**Extraction never computes.** It records what a document *states*. Ratios,
runway, and margins are `audit.finance`'s job, in code, and D9 is explicit that
a model must not produce them. A value here is a reading, not a derivation.
"""

import base64
import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from anthropic.types import MessageParam
from pydantic import Field, field_validator

from app.ai.caching import cached_system
from app.ai.client import AiCallRecord, AiClient, AiResult, AiUsage, ModelTier
from app.ai.guards import UNTRUSTED_RULE, fence
from app.ai.prompts import PromptVersion, register
from app.ai.schemas import Citation, StructuredOutput
from app.modules.intake.fields import (
    PROFILE_FIELDS,
    FieldSource,
    FieldSpec,
    value_error,
)

__all__ = [
    "EXTRACTION_PROMPT",
    "ExtractedField",
    "ExtractionResult",
    "SourceDocument",
    "extract_fields",
    "merge_into_profile",
    "missing_required_fields",
]

_FIELDS_BY_NAME: Final[dict[str, FieldSpec]] = {
    spec.name: spec for spec in PROFILE_FIELDS
}

# Sent as native API blocks rather than parsed to text.
_NATIVE_DOCUMENT_TYPES: Final[frozenset[str]] = frozenset({"application/pdf"})
_NATIVE_IMAGE_TYPES: Final[frozenset[str]] = frozenset({"image/png", "image/jpeg"})

_MAX_TEXT_CHARACTERS: Final = 200_000
"""Per-document cap on inlined text.

A spreadsheet can hold a million cells of noise. This is not a token budget --
`AiClient` owns that -- it is a guard against one pathological upload crowding
every other document out of the same call.
"""


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """One uploaded document, already fetched.

    `document_id` is what a `Citation.source_id` must point back to, so it has
    to be the real persisted id and not the filename -- two documents can share
    a filename, and a citation that cannot be resolved to a row is not evidence.
    """

    document_id: str
    filename: str
    content_type: str
    content: bytes


class ExtractedField(StructuredOutput):
    """One profile field read out of a document."""

    name: str = Field(description="Profile field name. Must be one we asked for.")
    value: str = Field(
        min_length=1,
        description=(
            "The value exactly as the document states it. Numbers stay in the "
            "document's own units; do not convert, scale, or compute."
        ),
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "How certain this reading is. Below 0.5 means a guess worth "
            "surfacing to the founder for confirmation, not a fact."
        ),
    )
    citation: Citation = Field(
        description="The document and the exact span this value was read from."
    )

    @field_validator("name")
    @classmethod
    def _known_field(cls, value: str) -> str:
        """A field we do not have is a hallucinated one; reject it here.

        Dropping it silently later would leave the model's mistake invisible.
        """
        if value not in _FIELDS_BY_NAME:
            raise ValueError(f"unknown profile field '{value}'")
        return value


class ExtractionResult(StructuredOutput):
    """Everything one extraction pass read, plus what it could not read."""

    fields: list[ExtractedField] = Field(
        default_factory=list,
        description=(
            "One entry per field found. Omit a field entirely rather than "
            "guessing it -- a missing field is a known gap, a wrong one is not."
        ),
    )
    unreadable: list[str] = Field(
        default_factory=list,
        description=(
            "Document ids nothing could be read from, so the founder can be "
            "told which upload did not land."
        ),
    )


SYSTEM_PROMPT: Final = f"""\
You read uploaded business documents and report the Startup Profile fields they
state. You are a careful reader, not an analyst.

Rules:

* **Report only what a document states.** Never infer, estimate, average, or
  calculate. If a document gives monthly revenue and you are asked for annual,
  do not multiply -- omit the field. Derived figures are computed elsewhere, in
  code, and a calculated value arriving here as a reading is a false reading.
* **Every value carries a citation** naming the document id and quoting the
  exact span it came from. A value you cannot quote is a value you must omit.
* **Numbers keep the document's units.** Do not convert currency, do not scale
  thousands to units, do not normalise percentages. Quote what is written.
* **Omit rather than guess.** A field absent from the profile is a known gap the
  founder can fill. A wrong field is a wrong audit.
* Set `confidence` honestly. A figure in a labelled financial table is high; a
  number inferred from a chart axis is low.

{UNTRUSTED_RULE}
"""


EXTRACTION_PROMPT: Final = register(
    PromptVersion(name="profile_extraction", version=1, text=SYSTEM_PROMPT)
)
"""The registered, versioned prompt. Its `ref` is recorded on the AuditRun."""


def _field_catalogue() -> str:
    """The fields to look for, rendered once into the cached prefix."""
    lines = [
        f"* `{spec.name}` ({spec.kind.value}) -- {spec.description}"
        for spec in PROFILE_FIELDS
    ]
    return "## Fields to look for\n\n" + "\n".join(lines) + "\n"


CATALOGUE_PROMPT: Final = _field_catalogue()


# ---------------------------------------------------------------------------
# Reading documents
# ---------------------------------------------------------------------------


def _csv_to_text(content: bytes) -> str:
    """Rows as pipe-delimited lines.

    Re-emitted rather than passed through so a quoted cell containing the
    fence's closing tag cannot terminate the block early.
    """
    text = content.decode("utf-8", errors="replace")
    rows = csv.reader(io.StringIO(text))
    return "\n".join(" | ".join(cell.strip() for cell in row) for row in rows)


def _xlsx_to_text(content: bytes) -> str:
    """Every sheet, one row per line, empty cells skipped.

    `data_only=True` reads cached formula *results* rather than the formulas --
    `=B2*12` tells the model nothing about revenue.
    """
    import openpyxl

    book = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    out: list[str] = []
    try:
        for sheet in book.worksheets:
            out.append(f"### sheet: {sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                cells = [
                    str(c).strip() for c in row if c is not None and str(c).strip()
                ]
                if cells:
                    out.append(" | ".join(cells))
    finally:
        book.close()
    return "\n".join(out)


def _pptx_to_text(content: bytes) -> str:
    """Slide text frames and table cells, in slide order."""
    from pptx import Presentation

    deck = Presentation(io.BytesIO(content))
    out: list[str] = []
    for number, slide in enumerate(deck.slides, start=1):
        out.append(f"### slide {number}")
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                out.append(shape.text_frame.text.strip())
            if shape.has_table:
                for row in shape.table.rows:
                    cells = [
                        cell.text.strip() for cell in row.cells if cell.text.strip()
                    ]
                    if cells:
                        out.append(" | ".join(cells))
    return "\n".join(out)


def _docx_to_text(content: bytes) -> str:
    """Paragraphs and table cells."""
    import docx

    document = docx.Document(io.BytesIO(content))
    out = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                out.append(" | ".join(cells))
    return "\n".join(out)


_PARSERS: Final[dict[str, Any]] = {
    "text/csv": _csv_to_text,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": _xlsx_to_text,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
        _pptx_to_text
    ),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        _docx_to_text
    ),
}


def _bare_type(content_type: str) -> str:
    """`text/csv; charset=utf-8` -> `text/csv`, matching the upload allowlist."""
    return content_type.split(";")[0].strip().lower()


def _document_blocks(
    documents: Sequence[SourceDocument],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Turn documents into message content blocks.

    Returns the blocks and the ids of documents nothing could be read from --
    reported rather than dropped, so a founder learns which upload was wasted
    instead of wondering why a field stayed empty.
    """
    blocks: list[dict[str, Any]] = []
    unreadable: list[str] = []

    for document in documents:
        bare = _bare_type(document.content_type)
        label = f"{document.filename} (document_id: {document.document_id})"

        if bare in _NATIVE_DOCUMENT_TYPES:
            blocks.append(
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.standard_b64encode(document.content).decode(),
                    },
                    "title": label,
                }
            )
            continue

        if bare in _NATIVE_IMAGE_TYPES:
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": bare,
                        "data": base64.standard_b64encode(document.content).decode(),
                    },
                }
            )
            blocks.append({"type": "text", "text": f"(above image: {label})"})
            continue

        if bare in _PARSERS:
            try:
                text = _PARSERS[bare](document.content)
            except Exception:  # noqa: BLE001 -- a corrupt upload is data, not a bug
                unreadable.append(document.document_id)
                continue
            text = text.strip()[:_MAX_TEXT_CHARACTERS]
            if not text:
                unreadable.append(document.document_id)
                continue
            blocks.append({"type": "text", "text": fence(text, label=label).text})
            continue

        # On the upload allowlist but with no route in: the legacy binary
        # Office formats. Recorded, never silently ignored.
        unreadable.append(document.document_id)

    return blocks, unreadable


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


async def extract_fields(
    client: AiClient,
    *,
    documents: Sequence[SourceDocument],
    known_facts: str = "",
    user_id: str | None = None,
) -> AiResult[ExtractionResult]:
    """Read Startup Profile fields out of a set of documents.

    `known_facts` is what the founder already stated, rendered. It is passed so
    the model can corroborate rather than contradict, and it is **not** a
    licence to echo those values back: a field the founder already supplied is
    theirs, and `merge_into_profile` will keep it regardless.

    Argument order mirrors `rubric.v1.score` and is the cache ordering, not
    style: the prompt and the field catalogue are identical on every call and
    sit in the cached prefix; this startup's facts and its documents come after
    the breakpoint, documents last.
    """
    blocks, unreadable = _document_blocks(documents)

    if not blocks:
        # Nothing readable. Returning empty beats spending an audit-tier call to
        # be told so, and every id is already accounted for as unreadable. The
        # record is real but zero-cost -- `attempts=0` is the honest marker that
        # no request was made, and it keeps the caller's accounting uniform
        # instead of making a successful extraction optional.
        return AiResult(
            output=ExtractionResult(fields=[], unreadable=unreadable),
            record=AiCallRecord(
                tier=ModelTier.AUDIT,
                model=client.profile_for(ModelTier.AUDIT).model,
                prompt_ref=EXTRACTION_PROMPT.ref,
                user_id=user_id,
                occurred_at=datetime.now(UTC),
                usage=AiUsage(0, 0, 0, 0),
                attempts=0,
            ),
        )

    system = cached_system(EXTRACTION_PROMPT.text, CATALOGUE_PROMPT)

    facts = known_facts.strip() or "None supplied."
    request: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "Read the documents below and report every profile field they "
                "state.\n\n"
                "## Already supplied by the founder (for corroboration only)\n"
                f"{facts}\n\n"
                "## Documents"
            ),
        },
        *blocks,
    ]

    messages: list[MessageParam] = [{"role": "user", "content": request}]  # type: ignore[typeddict-item]

    result = await client.complete(
        tier=ModelTier.AUDIT,
        prompt=EXTRACTION_PROMPT,
        schema=ExtractionResult,
        system=system,
        messages=messages,
        user_id=user_id,
    )

    # Documents the reader could not open are known here, not to the model.
    # Union rather than replace: the model may also report one it could open
    # but found nothing usable in.
    merged = list(dict.fromkeys([*unreadable, *result.output.unreadable]))
    return AiResult(
        output=ExtractionResult(fields=result.output.fields, unreadable=merged),
        record=result.record,
    )


# ---------------------------------------------------------------------------
# Merging into a profile
# ---------------------------------------------------------------------------


def merge_into_profile(
    existing: dict[str, Any], extracted: ExtractionResult
) -> dict[str, Any]:
    """Fold extracted values into a profile's `fields` JSONB.

    **A founder-stated value always wins.** They know their own business, and
    silently overwriting what someone typed with what a model read off a slide
    is the fastest way to lose their trust in the audit. Extraction fills gaps
    and corrects nothing.

    Values that fail their `FieldSpec` are dropped: a `percent` of 4000 or a
    `year` of "soon" is a misreading, and storing it would push the failure into
    whatever reads the profile next.
    """
    merged = dict(existing)

    for field in extracted.fields:
        spec = _FIELDS_BY_NAME[field.name]

        current = merged.get(field.name)
        if isinstance(current, dict) and current.get("source") == FieldSource.FOUNDER:
            continue

        coerced = _coerce(spec, field.value)
        if coerced is None or value_error(spec, coerced) is not None:
            continue

        merged[field.name] = {
            "value": coerced,
            "source": FieldSource.DOCUMENT.value,
            "confidence": field.confidence,
            "citation": {
                "source_id": field.citation.source_id,
                "quote": field.citation.quote,
            },
        }

    return merged


def _coerce(spec: FieldSpec, raw: str) -> Any:
    """Bring a stated string to the field's own kind, or `None` if it will not go.

    The model is told to quote the document verbatim, so "1,200" and "45%"
    arrive as written. Parsing them here keeps that instruction honest -- asking
    for a clean number instead would invite the model to tidy a figure, which is
    one short step from adjusting it.
    """
    from app.modules.intake.fields import FieldKind

    text = raw.strip()
    if spec.kind is FieldKind.TEXT:
        return text or None

    if spec.kind is FieldKind.BOOLEAN:
        lowered = text.lower()
        if lowered in {"true", "yes", "y"}:
            return True
        if lowered in {"false", "no", "n"}:
            return False
        return None

    cleaned = text.replace(",", "").replace("%", "").strip()
    for symbol in ("$", "£", "€", "₦", "NGN", "USD", "GBP", "EUR", "AED"):
        cleaned = cleaned.replace(symbol, "")
    cleaned = cleaned.strip()

    try:
        if spec.kind is FieldKind.PERCENT:
            return float(cleaned)
        return int(float(cleaned))
    except (TypeError, ValueError):
        return None


def missing_required_fields(fields: dict[str, Any]) -> list[str]:
    """Which audit-required fields are still unfilled.

    Completeness is the audit's gate, not the profile's (`intake.models`), so
    this reports rather than rejects.
    """
    return [
        spec.name
        for spec in PROFILE_FIELDS
        if spec.required_for_audit
        and not (
            isinstance(fields.get(spec.name), dict)
            and fields[spec.name].get("value") not in (None, "")
        )
    ]
