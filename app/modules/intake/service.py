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

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.ownership import owned_or_404
from app.core.security import CurrentUser
from app.modules.intake.fields import REQUIRED_COLUMNS, REQUIRED_FIELDS
from app.modules.intake.models import StartupProfile
from app.modules.intake.repository import StartupProfileRepository

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


async def create_profile(
    session: AsyncSession, actor: CurrentUser, payload: dict[str, Any]
) -> StartupProfile:
    """Create the caller's own profile.

    `owner_id` comes from the verified token, never from the request body -- a
    client-supplied owner is how one founder's data ends up under another's
    account (CLAUDE.md section 4).
    """
    profiles = StartupProfileRepository(session)
    if await profiles.get_for_owner(actor.id) is not None:
        raise ConflictError("You already have a startup profile.")

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
