"""Database engine, session, and declarative base.

Connections use a least-privilege role and carry the end-user JWT so Postgres
row-level security applies (AUTH.md section 10). The Supabase service-role key
is server-only and is used solely by trusted server code.

Schema changes only ever happen through Alembic migrations (DECISIONS.md D13,
ARCHITECTURE.md section 6).

Implemented in TASKS.md T0.3.
"""
