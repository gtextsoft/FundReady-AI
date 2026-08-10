"""What may be uploaded, and the states an upload passes through (T1.5).

Policy, kept out of `models.py` and `service.py` so the acceptable-file rules
are one short list somebody can review without reading the upload flow -- the
same reason the profile field registry lives in `fields.py`.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

# 25 MiB. Sized for what the PRD actually asks for -- a pitch deck, a financial
# model, a cap table -- rather than for arbitrary files. Enforced *after* the
# upload by reading the object back, because a presigned PUT carries no policy
# conditions and the client's declared size is not evidence of anything.
MAX_UPLOAD_BYTES: Final[int] = 25 * 1024 * 1024


class DocumentKind(StrEnum):
    """What the founder says this file is.

    The three named in `fundready-prd.md` §4.1, a country-specific certificate
    of incorporation (T1.6), plus an escape hatch. It steers extraction
    (T2.4) -- a cap table and a financial model are read for different
    things -- so it is the founder's declaration, not a fact, and extraction
    must cope with being told the wrong one.

    A registration certificate is still self-reported evidence
    (`DECISIONS.md` D7): extraction reads legal name and registration number
    off it with a citation; nothing is labelled verified.
    """

    DECK = "deck"
    FINANCIALS = "financials"
    CAP_TABLE = "cap_table"
    REGISTRATION_CERTIFICATE = "registration_certificate"
    OTHER = "other"


class DocumentStatus(StrEnum):
    """Where an upload has got to."""

    # The row exists and a signed URL was issued; the object may not be there.
    PENDING = "pending"
    # Confirmed present in R2, within size, and of an accepted type.
    READY = "ready"
    # Arrived but failed validation. The object was deleted; the row is kept so
    # the founder is told why instead of watching an upload vanish.
    REJECTED = "rejected"


class ScanStatus(StrEnum):
    """Malware scanning (`CLAUDE.md` §4: uploads are scanned).

    **No scanner is wired yet.** `intake.service.scan_document` is the seam it
    plugs into; the queue it will run on arrives with T2.8, and the scanner
    itself is T5.5. Until then uploads settle at `SKIPPED`, which is honest --
    an unscanned file must not be recorded as `CLEAN`.
    """

    PENDING = "pending"
    CLEAN = "clean"
    INFECTED = "infected"
    SKIPPED = "skipped"


# Accepted MIME types, mapped to the extension a founder will recognise.
# An allowlist, never a blocklist: the interesting formats are the ones nobody
# thought to exclude.
#
# **This constrains what the client declares, not what the bytes are.** The
# signed URL pins `Content-Type`, and R2 records what was sent -- an attacker
# can label anything `application/pdf`. Deciding what a file really is means
# reading its magic bytes, which belongs to the scan step. This list keeps
# honest clients honest and keeps obvious rubbish out of extraction.
ALLOWED_CONTENT_TYPES: Final[dict[str, str]] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.ms-powerpoint": "ppt",
    "application/msword": "doc",
    "text/csv": "csv",
    # Founders photograph cap tables and signed pages more often than anyone
    # would like.
    "image/png": "png",
    "image/jpeg": "jpg",
}


@dataclass(frozen=True, slots=True)
class DocumentPayload:
    """One stored document, fetched, as plain data.

    What the audit worker is handed instead of a `Document` row: the ORM object
    belongs to a session the worker closes before the model calls begin, and
    touching an attribute afterwards is a lazy load against a connection that is
    gone. Plain data also keeps `audit` from importing `intake.models`
    (`ARCHITECTURE.md` section 3) -- the composition root maps this into
    `audit.extraction.SourceDocument`.
    """

    document_id: str
    filename: str
    content_type: str
    content: bytes


def is_allowed_content_type(content_type: str) -> bool:
    """Whether this MIME type is on the allowlist.

    Compares the bare type: browsers append parameters (`text/csv;
    charset=utf-8`) and a founder's upload must not fail over an encoding hint.
    """
    return content_type.split(";")[0].strip().lower() in ALLOWED_CONTENT_TYPES


__all__ = [
    "ALLOWED_CONTENT_TYPES",
    "MAX_UPLOAD_BYTES",
    "DocumentKind",
    "DocumentPayload",
    "DocumentStatus",
    "ScanStatus",
    "is_allowed_content_type",
]
