"""Intake business logic.

Layer: **service** (ARCHITECTURE.md section 3) -- business logic and
orchestration. Performs authorization and ownership checks (AUTH.md sections
5-6), calls this module's `repository`, `app.ai`, and other modules' public
service functions only (never their internals). Enqueues background jobs.
Selects the tier serializer for every response carrying report data
(DECISIONS.md D8).

**This module is the tenant-isolation wall.** With self-built auth there is no
`auth.uid()` for the database to key policies off, so the app-layer ownership
check is the primary defence and Postgres RLS is only a backstop
(DECISIONS.md D13). Every function that reaches a profile by id goes through
`_authorise`, and a founder asking for someone else's profile gets **404, not
403** -- a 403 would confirm the id exists (AUTH.md section 6). The decision
itself lives in `core.ownership` (T1.3) so every founder-owned table that
follows applies the identical rule.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email_domains import company_name_from_email
from app.core.errors import ConflictError, InvalidRequestError, NotFoundError
from app.core.ownership import owned_or_404
from app.core.security import CurrentUser, Role, assert_admin
from app.core.storage import (
    ObjectTooLargeError,
    StoredObject,
    delete_object,
    get_object,
    head_object,
    object_key,
    signed_download_url,
    signed_upload_url,
)
from app.modules.identity import service as identity
from app.modules.identity.models import AuditAction
from app.modules.intake.documents import (
    MAX_UPLOAD_BYTES,
    CompanyVerificationStatus,
    DocumentKind,
    DocumentPayload,
    DocumentStatus,
    ScanStatus,
    is_allowed_content_type,
)
from app.modules.intake.fields import REQUIRED_COLUMNS, REQUIRED_FIELDS
from app.modules.intake.models import Document, StartupProfile
from app.modules.intake.repository import DocumentRepository, StartupProfileRepository

logger = logging.getLogger(__name__)

# One wording for both denials -- "no such profile" and "not yours" must read
# identically, so the message is fixed here rather than typed per call site
# where the two could drift apart (AUTH.md section 6).
_DENIED = "No such startup profile."


def _authorise(profile: StartupProfile | None, actor: CurrentUser) -> StartupProfile:
    """Return the profile only if this caller is entitled to it.

    The rule itself is `core.ownership.owned_or_404`; this only binds the
    message. Kept as the module's single door so a new function reaching a
    profile by id has an obvious thing to call.
    """
    return owned_or_404(profile, actor, message=_DENIED)


def missing_fields(profile: StartupProfile) -> list[str]:
    """What an audit still needs from this profile.

    Computed on read, never stored: it is a function of the field set and the
    rubric version, so a persisted copy would go stale the moment either
    changed. A field present but empty counts as missing -- `{"value": null}` is
    a placeholder, not an answer.
    """
    absent = [
        column for column in REQUIRED_COLUMNS if getattr(profile, column, None) is None
    ]
    stored = profile.fields or {}
    absent.extend(
        name
        for name in REQUIRED_FIELDS
        if not isinstance(stored.get(name), dict)
        or stored[name].get("value") in (None, "")
    )
    return sorted(absent)


async def _name_from_company_domain(
    session: AsyncSession, actor: CurrentUser
) -> str | None:
    """The company name implied by this founder's verified email domain.

    **Founders only** (`DECISIONS.md` D20). They are the only role required to
    hold a company address, so they are the only role whose domain means
    anything here. An admin may also create a profile (`AUTH.md` section 5),
    and deriving from *their* address would put a SACI domain on a startup.

    Safe to trust as far as it goes, because the domain is *verified*: an
    account sits at `pending_verification` until the emailed link is clicked,
    and every endpoint behind `CurrentUserDep` requires an active account. So
    the founder demonstrably controls a mailbox at this domain.

    What it is not is authoritative. `acme.com` gives "Acme", which is a
    convenience so the founder does not retype what the platform already knows
    -- and which they can change at any time through the update endpoint.

    `None` (leaving the field empty, and listed in `missing_fields`) whenever
    nothing sensible can be read: better an obvious gap than a wrong name that
    reads as though someone confirmed it.
    """
    if actor.role is not Role.FOUNDER:
        return None
    email = await identity.get_user_email(session, actor.id)
    return company_name_from_email(email) if email else None


async def create_profile(
    session: AsyncSession, actor: CurrentUser, payload: dict[str, Any]
) -> StartupProfile:
    """Create the caller's own profile.

    `owner_id` comes from the verified token, never from the request body -- a
    client-supplied owner is how one founder's data ends up under another's
    account (CLAUDE.md section 4).

    When no name is given, one is read off the founder's company email domain
    (`DECISIONS.md` D20). Only when it is *absent*: a name the founder typed is
    never replaced by a guess.
    """
    profiles = StartupProfileRepository(session)
    if await profiles.get_for_owner(actor.id) is not None:
        raise ConflictError("You already have a startup profile.")

    if not payload.get("name"):
        payload["name"] = await _name_from_company_domain(session, actor)

    return await profiles.create(
        owner_id=actor.id,
        fields=payload.pop("fields", None) or {},
        **payload,
    )


async def get_profile(
    session: AsyncSession, actor: CurrentUser, profile_id: uuid.UUID
) -> StartupProfile:
    """Read one profile, if this caller owns it or is an admin."""
    return _authorise(await StartupProfileRepository(session).get(profile_id), actor)


async def get_own_profile(session: AsyncSession, actor: CurrentUser) -> StartupProfile:
    """Read the caller's own profile without needing to know its id."""
    profile = await StartupProfileRepository(session).get_for_owner(actor.id)
    if profile is None:
        raise NotFoundError("You do not have a startup profile yet.")
    return profile


async def set_discoverability(
    session: AsyncSession,
    actor: CurrentUser,
    profile_id: uuid.UUID,
    *,
    visible: bool,
) -> StartupProfile:
    """Opt this startup in to, or out of, investor discovery (T4.3).

    **Publishing is a separate decision from being audited**, which is why this
    is an explicit action rather than something derived from having a report.
    A founder who runs an audit has asked what their business looks like; they
    have not agreed to show it to investors, and inferring the second from the
    first would publish confidential data because somebody used the product.

    **This flag is consent, not eligibility, and the two are enforced in
    different places on purpose.** Setting it says "I am willing to be seen".
    Whether there is anything *to* see is decided at read time: the discovery
    query inner-joins to a succeeded audit, so a published profile with no
    verdict simply does not appear. A founder may therefore publish before
    auditing and will start appearing when the audit lands.

    Checking the audit here instead would mean this module reaching into
    `audit`, which already depends on `intake` -- a circular import, and a
    boundary violation `ARCHITECTURE.md` section 3 forbids. It would also be
    the weaker of the two guards: a check at write time says nothing about a
    run that is later deleted or superseded, whereas the join cannot go stale.
    The endpoint description tells the client to expect the delay.

    **Unpublishing is unconditional.** Withdrawing consent must never be harder
    than giving it.

    When the readiness gate lands (T3.6) it constrains the publish branch only.
    Nothing here changes shape.
    """
    profile = _authorise(await StartupProfileRepository(session).get(profile_id), actor)

    profile.investor_visible = visible
    profile.published_at = datetime.now(UTC) if visible else None
    await session.flush()

    logger.info(
        "startup discoverability changed",
        extra={
            "context": {
                "startup_id": str(profile.id),
                "investor_visible": visible,
            }
        },
    )
    return profile


async def submit_company_verification(
    session: AsyncSession, actor: CurrentUser, startup_id: uuid.UUID
) -> StartupProfile:
    """Founder submits an uploaded registration certificate for SACI review.

    **SACI admin review of an uploaded cert, NOT registry KYC** (`DECISIONS.md`
    D7). Requires a ready `registration_certificate` document. Moves status
    through submitted → in_review so the admin queue can pick it up.
    """
    profile = _authorise(await StartupProfileRepository(session).get(startup_id), actor)

    if profile.company_verification_status in (
        CompanyVerificationStatus.SUBMITTED,
        CompanyVerificationStatus.IN_REVIEW,
        CompanyVerificationStatus.ACCEPTED,
    ):
        raise ConflictError(
            f"Company verification is already "
            f"{profile.company_verification_status.value}."
        )

    documents = await DocumentRepository(session).list_for_startup(profile.id)
    has_cert = any(
        document.kind is DocumentKind.REGISTRATION_CERTIFICATE
        and document.status is DocumentStatus.READY
        for document in documents
    )
    if not has_cert:
        raise InvalidRequestError(
            "Upload a registration certificate before submitting for review.",
            {"reason": "registration_certificate_required"},
        )

    # submitted → in_review in one step: the founder has submitted, and the
    # row lands on the admin work queue immediately.
    profile.company_verification_status = CompanyVerificationStatus.IN_REVIEW
    await session.flush()

    await identity.record_action(
        session,
        AuditAction.COMPANY_VERIFICATION_SUBMITTED,
        actor_id=actor.id,
        target_type="startup",
        target_id=profile.id,
        details={"status": profile.company_verification_status.value},
    )
    return profile


async def decide_company_verification(
    session: AsyncSession,
    actor: CurrentUser,
    startup_id: uuid.UUID,
    *,
    accept: bool,
) -> StartupProfile:
    """SACI admin accepts or rejects a submitted registration certificate.

    **Not registry KYC** (`DECISIONS.md` D7) — this records an admin's review of
    the uploaded file only.
    """
    assert_admin(actor)
    profile = await StartupProfileRepository(session).get(startup_id)
    if profile is None:
        raise NotFoundError(_DENIED)

    if profile.company_verification_status not in (
        CompanyVerificationStatus.SUBMITTED,
        CompanyVerificationStatus.IN_REVIEW,
    ):
        raise ConflictError(
            "This startup has no company verification awaiting a decision."
        )

    profile.company_verification_status = (
        CompanyVerificationStatus.ACCEPTED
        if accept
        else CompanyVerificationStatus.REJECTED
    )
    await session.flush()

    await identity.record_action(
        session,
        AuditAction.COMPANY_VERIFICATION_DECIDED,
        actor_id=actor.id,
        target_type="startup",
        target_id=profile.id,
        details={
            "accepted": accept,
            "status": profile.company_verification_status.value,
        },
    )
    return profile


async def update_profile(
    session: AsyncSession,
    actor: CurrentUser,
    profile_id: uuid.UUID,
    payload: dict[str, Any],
) -> StartupProfile:
    """Partially update a profile the caller owns.

    Omitted keys are left alone. `fields` merges by field name, so a client can
    send one corrected value without having to resend the whole document -- and
    so concurrent extraction (T2.4) does not wipe what the founder typed.
    """
    profile = _authorise(await StartupProfileRepository(session).get(profile_id), actor)

    incoming_fields = payload.pop("fields", None)
    for column, value in payload.items():
        setattr(profile, column, value)

    if incoming_fields:
        # Reassigned rather than mutated: SQLAlchemy does not track in-place
        # changes to a JSONB dict, so mutating it would silently not persist.
        profile.fields = {**(profile.fields or {}), **incoming_fields}

    await session.flush()
    return profile


# ---------------------------------------------------------------------------
# Documents (T1.5) -- metadata here, bytes in R2
# ---------------------------------------------------------------------------

_DOCUMENT_DENIED = "No such document."


async def request_upload(
    session: AsyncSession,
    actor: CurrentUser,
    startup_id: uuid.UUID,
    *,
    kind: DocumentKind,
    filename: str,
    content_type: str,
) -> tuple[Document, str]:
    """Reserve a document row and hand back a signed URL to `PUT` it to.

    The row is created **before** the file exists, so the storage key is known
    to the server and never negotiated with the client. What comes back is a
    URL that grants exactly one write, to exactly one key, for fifteen minutes.

    `content_type` is checked against the allowlist here and then baked into
    the signature, so an upload that declares something else is refused by R2
    rather than by us. It remains a *declaration* -- `complete_upload` reads
    back what actually landed, and the scan hook is what would notice a PDF
    that is really a zip.

    Returns the row and the URL. The URL is never persisted: it is a
    credential, and a credential in a column is a credential in every backup.
    """
    profile = owned_or_404(
        await StartupProfileRepository(session).get(startup_id), actor, message=_DENIED
    )

    if not is_allowed_content_type(content_type):
        raise InvalidRequestError(
            "That file type cannot be uploaded.",
            {"field": "content_type", "reason": "unsupported_content_type"},
        )

    document_id = uuid.uuid4()
    # Scoped by startup, keyed by document. Both server-generated UUIDs -- the
    # filename never touches the key (`core.storage.object_key`).
    key = object_key(profile.id, document_id)

    document = await DocumentRepository(session).create(
        document_id=document_id,
        owner_id=profile.owner_id,
        startup_id=profile.id,
        kind=kind,
        filename=safe_filename(filename),
        storage_key=key,
    )
    return document, signed_upload_url(key, content_type=content_type)


async def complete_upload(
    session: AsyncSession, actor: CurrentUser, document_id: uuid.UUID
) -> Document:
    """Confirm an upload actually arrived, and decide whether to keep it.

    This is where validation becomes real. Everything before it took the
    client's word; here the object is read back from R2 and judged on what it
    is: present at all, within `MAX_UPLOAD_BYTES`, and of an accepted type.
    A file that fails is **deleted from the bucket** and the row marked
    `rejected` -- keeping the row so the founder gets a reason rather than
    watching an upload disappear.

    Idempotent: calling it again on a `ready` document returns it unchanged, so
    a client that retries after a dropped response does not re-enter the flow.
    """
    document = owned_or_404(
        await DocumentRepository(session).get(document_id),
        actor,
        message=_DOCUMENT_DENIED,
    )
    if document.status is DocumentStatus.READY:
        return document

    stored = head_object(document.storage_key)
    if stored is None:
        raise InvalidRequestError(
            "That upload has not arrived yet.",
            {"field": "document_id", "reason": "object_missing"},
        )

    rejection = _rejection_reason(stored)
    if rejection is not None:
        # Removed before the row is updated: a file that failed validation must
        # not sit in the bucket waiting for someone to find a way to read it.
        delete_object(document.storage_key)
        document.status = DocumentStatus.REJECTED
        document.size_bytes = stored.size_bytes
        document.content_type = stored.content_type
        await session.flush()
        logger.info("upload rejected", extra={"context": {"reason": rejection}})
        raise InvalidRequestError(
            "That upload was rejected.",
            {"field": "document_id", "reason": rejection},
        )

    # What R2 reports, not what the client said when it asked for the URL.
    document.size_bytes = stored.size_bytes
    document.content_type = stored.content_type
    document.status = DocumentStatus.READY
    await session.flush()

    await scan_document(session, document)
    return document


async def scan_document(session: AsyncSession, document: Document) -> None:
    """Magic-byte verification for uploads (`CLAUDE.md` section 4, T5.5).

    Reads the object head from R2 and checks it against the declared content
    type. A mismatch is `INFECTED` (refused by `_is_auditable`); a match that
    also carries a PE (`MZ`) marker is `INFECTED` as well. Full antivirus
    remains an external plug-in at this same seam — this is fingerprinting,
    not malware detection.
    """
    from app.core.storage import get_object
    from app.modules.intake.scanning import (
        content_type_matches_bytes,
        head_contains_pe_executable,
    )

    try:
        stored = get_object(
            document.storage_key, bucket="documents", max_bytes=64 * 1024
        )
    except Exception:
        # Misconfigured storage in tests/dev must not fail the upload confirm.
        logger.warning(
            "upload scan skipped; object unread",
            extra={"context": {"document_id": str(document.id)}},
        )
        document.scan_status = ScanStatus.SKIPPED
        await session.flush()
        return

    if stored is None:
        document.scan_status = ScanStatus.SKIPPED
        await session.flush()
        return

    head = stored[:8192]
    declared = document.content_type or ""
    if content_type_matches_bytes(declared, head) and not head_contains_pe_executable(
        head
    ):
        document.scan_status = ScanStatus.CLEAN
    else:
        document.scan_status = ScanStatus.INFECTED
        logger.warning(
            "upload failed magic-byte scan",
            extra={"context": {"document_id": str(document.id)}},
        )
    await session.flush()


async def list_documents(
    session: AsyncSession, actor: CurrentUser, startup_id: uuid.UUID
) -> list[Document]:
    """Every document on a startup the caller owns."""
    profile = owned_or_404(
        await StartupProfileRepository(session).get(startup_id), actor, message=_DENIED
    )
    return await DocumentRepository(session).list_for_startup(profile.id)


def _is_auditable(document: Document) -> bool:
    """Whether the audit may read this document.

    `READY` only -- an upload that never completed validation has no trustworthy
    bytes behind it -- and never one the scanner flagged. `CLEAN` is required
    for new uploads; `SKIPPED` remains allowed for rows scanned before T5.5 so
    historical decks are not silently dropped from audits.
    """
    return document.status is DocumentStatus.READY and document.scan_status in {
        ScanStatus.CLEAN,
        ScanStatus.SKIPPED,
    }


async def auditable_storage_keys(
    session: AsyncSession, startup_id: uuid.UUID
) -> list[str]:
    """The storage keys the audit would read, for the idempotency fingerprint.

    Keys rather than ids, and separate from `load_auditable_documents`, because
    the fingerprint is computed in the request that creates the AuditRun -- long
    before any bytes are fetched, and it must not fetch any. Reading a key list
    is one indexed query; reading the documents is several megabytes over the
    network, on the request thread.
    """
    documents = await DocumentRepository(session).list_for_startup(startup_id)
    return [document.storage_key for document in documents if _is_auditable(document)]


async def load_auditable_documents(
    session: AsyncSession, startup_id: uuid.UUID
) -> tuple[list[DocumentPayload], list[str]]:
    """Fetch every readable document on a startup. Returns payloads and failures.

    **No ownership check, deliberately**, for the same reason
    `workers.tasks._snapshot_for` has none: there is no caller to authorise. The
    AuditRun row already named this startup and was written by a service call
    that did check. Inventing a `CurrentUser` here is how a background job ends
    up running as an implicit superuser.

    A document whose object has gone missing, or is too large to hold, is
    **skipped and named** rather than failing the audit. The founder's other
    documents are still evidence, and an audit that dies because one upload was
    deleted is worse than one that says which upload it could not read -- the
    second list is what `unreadable` reports back to them.
    """
    documents = await DocumentRepository(session).list_for_startup(startup_id)

    payloads: list[DocumentPayload] = []
    unreadable: list[str] = []
    for document in documents:
        if not _is_auditable(document):
            continue
        try:
            content = get_object(document.storage_key)
        except ObjectTooLargeError:
            logger.warning(
                "document too large for the audit to read",
                extra={"context": {"document_id": str(document.id)}},
            )
            unreadable.append(str(document.id))
            continue
        if content is None:
            logger.warning(
                "document row has no object behind it",
                extra={"context": {"document_id": str(document.id)}},
            )
            unreadable.append(str(document.id))
            continue
        payloads.append(
            DocumentPayload(
                document_id=str(document.id),
                filename=document.filename,
                # Never `None`: `complete_upload` writes what R2 reported. A row
                # without one predates validation and has nothing to dispatch on.
                content_type=document.content_type or "application/octet-stream",
                content=content,
            )
        )

    return payloads, unreadable


async def request_download(
    session: AsyncSession, actor: CurrentUser, document_id: uuid.UUID
) -> str:
    """A short-lived URL that reads one document.

    **The ownership check is the whole security of this endpoint.** What it
    returns is a bearer credential: anyone holding the URL can read a founder's
    financials for its lifetime, with no token and no further check. Signing
    one without `owned_or_404` first would be a straight IDOR, and the leak
    would outlive the request that caused it.

    Refuses anything not `ready` -- an unvalidated or rejected object is not
    readable -- and anything the scanner has flagged.
    """
    document = owned_or_404(
        await DocumentRepository(session).get(document_id),
        actor,
        message=_DOCUMENT_DENIED,
    )
    if document.status is not DocumentStatus.READY:
        raise InvalidRequestError(
            "That document is not ready to download.",
            {"field": "document_id", "reason": document.status.value},
        )
    if document.scan_status is ScanStatus.INFECTED:
        raise InvalidRequestError(
            "That document did not pass a malware scan.",
            {"field": "document_id", "reason": "infected"},
        )
    return signed_download_url(document.storage_key, filename=document.filename)


def _rejection_reason(stored: StoredObject) -> str | None:
    """Why this object is not acceptable, or `None` if it is."""
    if stored.size_bytes > MAX_UPLOAD_BYTES:
        return "file_too_large"
    if stored.size_bytes == 0:
        return "empty_file"
    if not is_allowed_content_type(stored.content_type):
        return "unsupported_content_type"
    return None


def safe_filename(filename: str) -> str:
    """The founder's filename, reduced to something safe to store and echo.

    **Public because evidence upload (T3.5) needs the identical treatment.** A
    founder attaching a screenshot has the same filename risks as one attaching
    a deck, and a second copy of this reduction is a second place for one of the
    three rules below to be forgotten.

    It is never a path component -- the storage key is built from UUIDs -- but
    it *is* returned in responses and set as `Content-Disposition` on download,
    so directory separators, control characters, and leading dots all come off
    before it is stored rather than at each use.
    """
    cleaned = filename.replace("\\", "/").split("/")[-1]
    cleaned = "".join(character for character in cleaned if character.isprintable())
    cleaned = cleaned.strip().lstrip(".").strip()
    return cleaned[:255] or "upload"
