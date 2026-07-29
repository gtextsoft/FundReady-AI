"""Migration graph integrity.

No database required. These catch the two ways a migration history goes wrong
on a team: a fork with two heads, which makes `upgrade head` ambiguous and
usually only appears after a merge, and a revision that cannot be rolled back.
"""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import Script, ScriptDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def scripts() -> ScriptDirectory:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return ScriptDirectory.from_config(config)


@pytest.fixture(scope="module")
def revisions(scripts: ScriptDirectory) -> list[Script]:
    return list(scripts.walk_revisions())


def test_exactly_one_head(scripts: ScriptDirectory) -> None:
    """Two heads means the history forked and `upgrade head` is ambiguous."""
    heads = scripts.get_heads()

    assert len(heads) == 1, f"expected a single head, found {heads}"


def test_there_is_at_least_the_baseline(revisions: list[Script]) -> None:
    assert revisions


def test_every_revision_explains_itself(revisions: list[Script]) -> None:
    """A migration is read months later by someone deciding whether to revert it."""
    for revision in revisions:
        assert revision.doc, f"{revision.revision} has no docstring"


def test_every_revision_is_reversible(revisions: list[Script]) -> None:
    """A migration that cannot be undone is one you cannot safely deploy."""
    for revision in revisions:
        source = Path(str(revision.path)).read_text(encoding="utf-8")
        _, _, downgrade = source.partition("def downgrade()")

        assert downgrade, f"{revision.revision} has no downgrade()"
        assert "NotImplementedError" not in downgrade, (
            f"{revision.revision} has an unimplemented downgrade"
        )
