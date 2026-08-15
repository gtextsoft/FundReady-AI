"""Object-level ownership -- the primary tenant-isolation wall (T1.3).

Per `DECISIONS.md` **D13**, this check *is* tenant isolation. With self-built
auth (D4) the database has no independent notion of the caller, so Postgres RLS
can only enforce what the application tells it; RLS is a backstop behind this
function, not a substitute for it (`AUTH.md` sections 6 and 10). **A missing
ownership check is a security bug even if RLS would have caught it** -- and
today RLS is not even present: the deployed role carries `BYPASSRLS`, so the
policies are deferred to T5.7 with a least-privilege role (`DECISIONS.md` D19).

It lives in `core` rather than in one module because every founder-owned table
that follows -- documents (T1.5), tasks (T3.1), evidence (T3.5) -- needs the
identical decision, and a check that is re-typed per module is a check that
eventually gets typed wrong. One implementation, one test suite, one place to
change if the rule changes.

Two properties are worth stating outright, because both are easy to lose in a
rewrite and neither is obvious from the signature:

* **Absent and forbidden are the same answer.** `NotFoundError` for both, with
  the caller's own message, so the two cannot be told apart by status code or
  body. Returning 403 for another tenant's id turns any endpoint into an
  existence oracle: an attacker walking ids learns which are real without ever
  reading a row (`AUTH.md` section 6).
* **The caller comes from the verified token, never from the request.** This
  function takes a `CurrentUser` for exactly that reason -- there is no
  parameter through which a client-supplied owner could arrive.

There is deliberately no variant for investor party-membership (`AUTH.md`
section 6, interests and meetings). Those models do not exist until T4.5, and a
second branch written now would be a guess about a shape nobody has designed.
"""

import logging
import uuid
from typing import Protocol, TypeVar

from app.core.errors import NotFoundError
from app.core.security import CurrentUser, Role, assert_admin

logger = logging.getLogger(__name__)


class HasOwner(Protocol):
    """Anything belonging to exactly one user.

    Read-only on purpose: this function decides access, and nothing about
    deciding access requires the power to reassign an owner.
    """

    @property
    def owner_id(self) -> uuid.UUID: ...


OwnedT = TypeVar("OwnedT", bound=HasOwner)


def owned_or_404(
    resource: OwnedT | None,
    actor: CurrentUser,
    *,
    message: str,
) -> OwnedT:
    """Return `resource` only if this caller is entitled to it.

    Takes `OwnedT | None` rather than a loaded row so the "no such row" and
    "not yours" cases are settled together, in one call, by one rule. Splitting
    them across a `None` check at the call site and an ownership check here is
    how the two answers drift apart and start leaking which ids exist.

    `message` is required and has no default: the wording is what the client
    actually sees, and every message for a given resource must be identical
    whether the row is missing or merely someone else's.

    SACI admins are exempt (`AUTH.md` section 2) -- the role that reveals full
    reports necessarily reads across tenants. Investors are not exempt; they
    reach startups through the summary serializer in T4.2, never through an
    owned-object read.

    Raises:
        NotFoundError: the resource does not exist, or does not belong to this
            caller. Indistinguishable by design.
    """
    if resource is None:
        raise NotFoundError(message)
    if actor.role is Role.ADMIN:
        # Cross-tenant reads are an admin capability (AUTH.md section 9).
        assert_admin(actor)
        return resource
    if resource.owner_id != actor.id:
        # Role only. Logging the actor id, the resource id, or the owner id
        # would put a map of who-tried-to-read-whose into the log stream, which
        # is a lower-trust store than the database it describes.
        logger.info(
            "cross-tenant access refused",
            extra={"context": {"actor_role": actor.role.value}},
        )
        raise NotFoundError(message)
    return resource


__all__ = ["HasOwner", "owned_or_404"]
