"""Mint a verification or password-reset link for local development.

    python scripts/issue_dev_token.py founder@example.test
    python scripts/issue_dev_token.py founder@example.test --purpose password_reset

Why this exists: auth tokens are stored hashed, so once one is emailed it cannot
be recovered from the database, and the application deliberately does not log
it -- `core.logging.RedactionFilter` scrubs `token=` from every log line because
a verification token is a credential. Rather than carve an exception into that
rule, local flows mint a fresh token here, outside the request path, where the
value is printed once to a terminal and never enters a log.

Refuses to run against production.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_session_factory  # noqa: E402
from app.modules.identity import service  # noqa: E402
from app.modules.identity.models import TokenPurpose  # noqa: E402
from app.modules.identity.repository import UserRepository  # noqa: E402

TTLS = {
    TokenPurpose.EMAIL_VERIFICATION: service.VERIFICATION_TTL,
    TokenPurpose.PASSWORD_RESET: service.PASSWORD_RESET_TTL,
}
PATHS = {
    TokenPurpose.EMAIL_VERIFICATION: "verify-email",
    TokenPurpose.PASSWORD_RESET: "reset-password",
}


async def issue(email: str, purpose: TokenPurpose) -> int:
    settings = get_settings()
    if settings.is_production:
        print("refusing to run against production", file=sys.stderr)
        return 2

    async with get_session_factory()() as session:
        user = await UserRepository(session).get_by_email(
            service.normalise_email(email)
        )
        if user is None:
            print(f"no account for {email}", file=sys.stderr)
            return 1

        raw = await service.issue_auth_token(session, user, purpose, TTLS[purpose])
        await session.commit()

    base = settings.app_link_base_url.rstrip("/") or "https://app.example"
    print(f"{base}/{PATHS[purpose]}?token={raw}")
    print(f"\nPOST the token to /v1/auth/{PATHS[purpose]} (expires in {TTLS[purpose]})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    parser.add_argument(
        "--purpose",
        choices=[p.value for p in TokenPurpose],
        default=TokenPurpose.EMAIL_VERIFICATION.value,
    )
    args = parser.parse_args()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(issue(args.email, TokenPurpose(args.purpose)))


if __name__ == "__main__":
    raise SystemExit(main())
