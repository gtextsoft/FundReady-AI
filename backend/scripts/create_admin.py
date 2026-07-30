"""Create the first admin account.

    python scripts/create_admin.py admin@saci.example

Admins are provisioned by other admins (`POST /v1/admin/users`), which leaves
the first one impossible to create through the API. This script closes that
circle, and it is the only thing that can: there is deliberately no
env-gated bootstrap endpoint, because that is a permanent attack surface which
exists to be misconfigured exactly once. This requires database credentials
instead -- already the trust boundary.

The account is created exactly as the API would create it:

* `pending_verification`, so the address must be confirmed
* **no MFA**, so `require_role(ADMIN)` refuses every admin capability until a
  second factor is enrolled (AUTH.md section 9)

It therefore grants no power on its own. Refuses to create a second admin --
after the first, use the API, so the action is attributable in the audit log.
"""

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import get_session_factory  # noqa: E402
from app.core.security import AccountStatus, Role, hash_password  # noqa: E402
from app.modules.identity import service  # noqa: E402
from app.modules.identity.models import AuditAction  # noqa: E402
from app.modules.identity.repository import UserRepository  # noqa: E402


async def create(email: str, password: str) -> int:
    normalised = service.normalise_email(email)
    try:
        service.validate_password(password, normalised)
    except Exception as error:  # noqa: BLE001 - message is for a human
        print(f"password rejected: {error}", file=sys.stderr)
        return 1

    async with get_session_factory()() as session:
        users = UserRepository(session)

        # Any admin at all, not just an active one: the first bootstrapped
        # admin is pending_verification until they confirm their address.
        if await users.count_admins(active_only=False) > 0:
            print(
                "an admin already exists -- use POST /v1/admin/users so the "
                "action is attributable",
                file=sys.stderr,
            )
            return 1
        if await users.get_by_email(normalised) is not None:
            print(f"{normalised} already has an account", file=sys.stderr)
            return 1

        admin = await users.create(
            email=normalised,
            password_hash=hash_password(password),
            role=Role.ADMIN,
            status=AccountStatus.PENDING_VERIFICATION,
        )
        # actor_id is the admin themselves: no other actor exists to credit.
        await service.record_action(
            session,
            AuditAction.ADMIN_PROVISIONED,
            actor_id=admin.id,
            target_type="user",
            target_id=admin.id,
            details={"bootstrap": True},
        )
        await session.commit()

    print(f"created admin {normalised}")
    print("\nNext, in order:")
    print("  1. verify the email address  (scripts/issue_dev_token.py, or the email)")
    print("  2. log in                    (POST /v1/auth/login)")
    print("  3. enrol MFA                 (POST /v1/auth/mfa/enroll, then /confirm)")
    print("\nNo admin capability works until step 3 is done.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the first admin account.")
    parser.add_argument("email")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help=(
            "Read the password from stdin instead of prompting, for automated "
            "deployment. Never pass a password as an argument -- argv is "
            "visible to every process on the machine."
        ),
    )
    args = parser.parse_args()

    if args.password_stdin:
        # `getpass` on Windows reads the console directly and ignores a pipe, so
        # a prompt cannot be automated even when stdin is redirected.
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass.getpass("password (min 12 chars): ")
        if password != getpass.getpass("confirm: "):
            print("passwords do not match", file=sys.stderr)
            return 1

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(create(args.email, password))


if __name__ == "__main__":
    raise SystemExit(main())
