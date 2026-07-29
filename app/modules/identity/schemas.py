"""Identity request/response schemas.

Layer: **schemas** (ARCHITECTURE.md section 3) -- Pydantic request and response
models, including the per-tier response serializers (summary vs full). Unknown
or extra fields are rejected. Tier filtering lives here and is enforced by the
service, never by the client (DECISIONS.md D8).

`Role` and `AccountStatus` are defined in `core.security` rather than here:
authentication is a cross-cutting concern and `core` must not import a feature
module. They are re-exported so schemas and routers have one obvious place to
reach for them (AGENTS.md section 4 -- enums are enums, never magic strings).
"""

from app.core.security import AccountStatus, Role

__all__ = ["AccountStatus", "Role"]
