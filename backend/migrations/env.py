"""Alembic environment.

Migrations run **synchronously** even though the application is async. DDL
gains nothing from async, and a sync connection avoids the event-loop
constraint psycopg's async mode imposes on Windows development machines.

The connection URL is read from the environment through `app.core.config` --
never from `alembic.ini`, which is committed.
"""

import importlib
import pkgutil
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.modules
from app.core.db import Base, resolve_database_url

# Configures the `alembic` CLI's own logging (alembic.ini). Applies only to
# this process -- the API installs its own JSON logging at startup.
if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)


def _import_all_models() -> None:
    """Import every `models` module so `Base.metadata` is complete.

    Done by discovery rather than a hand-maintained import list: a forgotten
    import would make autogenerate silently emit a migration that drops the
    tables it could not see.
    """
    for module in pkgutil.walk_packages(app.modules.__path__, "app.modules."):
        if module.name.endswith(".models"):
            importlib.import_module(module.name)


_import_all_models()

target_metadata = Base.metadata

# `compare_type` and `compare_server_default` are off by default, which means
# autogenerate silently ignores a changed column type or default.
CONTEXT_OPTIONS = {
    "target_metadata": target_metadata,
    "compare_type": True,
    "compare_server_default": True,
}


def run_migrations_offline() -> None:
    """Emit SQL without connecting (`alembic upgrade head --sql`)."""
    context.configure(
        url=resolve_database_url(for_migrations=True),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **CONTEXT_OPTIONS,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    engine = create_engine(
        resolve_database_url(for_migrations=True),
        # NullPool: a migration run is short-lived and must not hold Neon
        # connections open after it finishes.
        poolclass=pool.NullPool,
    )
    with engine.connect() as connection:
        context.configure(connection=connection, **CONTEXT_OPTIONS)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
