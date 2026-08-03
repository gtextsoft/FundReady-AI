"""Write the OpenAPI spec to `docs/openapi.json`.

    python scripts/export_openapi.py

The spec is committed so a client developer can generate a typed client, diff
an API change in review, or import the collection into Postman **without
running this service** -- which needs Postgres, a JWT secret, and a checkout
they may not have. The mobile and admin-web developers are the audience
(`CLIENTS.md`), and neither works in this repo.

Committing generated output is a deliberate tradeoff: it can go stale, so
`tests/unit/test_client_guide.py::test_the_exported_spec_is_current` fails when
it does. Run this whenever an endpoint or schema changes, in the same commit --
`CLAUDE.md` section 8 requires docs to move with the code that changed them.

Sorted keys and a trailing newline keep the diff readable: a reviewer should see
the endpoint that changed, not a reshuffle of the whole file.
"""

import json
import os
import sys
from pathlib import Path

# The app validates settings at import. Export must work on a machine with no
# `.env` -- it reads no data and talks to nothing, so a placeholder is honest
# here rather than a way of dodging configuration.
os.environ.setdefault("JWT_SECRET", "x" * 40)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402

DESTINATION = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"


def main() -> int:
    spec = app.openapi()
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    DESTINATION.write_text(
        json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    operations = sum(len(methods) for methods in spec["paths"].values())
    schemas = len(spec["components"]["schemas"])
    print(
        f"wrote {DESTINATION}\n"
        f"  {len(spec['paths'])} paths, {operations} operations, {schemas} schemas"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
