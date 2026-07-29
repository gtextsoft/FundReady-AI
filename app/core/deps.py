"""Shared FastAPI dependencies.

Composes `config`, `db`, and `security` into the annotated dependencies routers
declare. Routers depend on the aliases here rather than reaching into those
modules directly, so a change to how a session or a current user is obtained is
a one-line change in one place.

Identity and role dependencies (`CurrentUser`, `require_role`,
`require_kyc_verified`, `require_active_subscription`) land in T0.4.
"""

from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.core.db import AsyncSession, get_session

SettingsDep = Annotated[Settings, Depends(get_settings)]
"""Process-wide settings."""

SessionDep = Annotated[AsyncSession, Depends(get_session)]
"""A transactional database session, committed on success, rolled back on error."""

__all__ = ["SessionDep", "SettingsDep"]
