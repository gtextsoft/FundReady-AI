"""The shared ownership check (T1.3).

`core.ownership.owned_or_404` is the primary tenant-isolation wall
(`DECISIONS.md` D13). Postgres RLS is not behind it yet -- the deployed role
carries `BYPASSRLS`, so policies are deferred to T5.7 (`DECISIONS.md` D19) --
which means for now this function is the *only* thing standing between one
founder's financials and another founder's request. It is tested on its own,
not just through `intake`, because every founder-owned table that follows
(documents T1.5, tasks T3.1, evidence T3.5) will call this exact code.

No database: the function takes any object exposing `owner_id`, so the rules
can be asserted directly. `test_startup_profile_ownership.py` covers the same
rules end-to-end through the intake service against real rows.
"""

import logging
import uuid
from dataclasses import dataclass

import pytest

from app.core.errors import ErrorCode, ForbiddenError, NotFoundError
from app.core.ownership import owned_or_404
from app.core.security import AccountStatus, CurrentUser, Role

pytestmark = pytest.mark.security

MESSAGE = "No such thing."


@dataclass
class Owned:
    """Stands in for any founder-owned row."""

    owner_id: uuid.UUID


def actor(
    role: Role = Role.FOUNDER,
    user_id: uuid.UUID | None = None,
    *,
    mfa_enabled: bool | None = None,
) -> CurrentUser:
    return CurrentUser(
        id=user_id or uuid.uuid4(),
        role=role,
        status=AccountStatus.ACTIVE,
        email_verified=True,
        # Cross-tenant admin reads require MFA (`owned_or_404` → `assert_admin`).
        mfa_enabled=(role is Role.ADMIN) if mfa_enabled is None else mfa_enabled,
    )


class TestTheOwnerGetsTheirRow:
    def test_owner_receives_the_resource(self) -> None:
        caller = actor()

        resource = Owned(owner_id=caller.id)

        assert owned_or_404(resource, caller, message=MESSAGE) is resource

    def test_the_same_object_comes_back_untouched(self) -> None:
        """A check, not a filter -- it must not substitute or copy the row."""
        caller = actor()
        resource = Owned(owner_id=caller.id)

        returned = owned_or_404(resource, caller, message=MESSAGE)

        assert returned.owner_id == caller.id


class TestEveryoneElseGetsNothing:
    def test_another_users_row_is_refused(self) -> None:
        resource = Owned(owner_id=uuid.uuid4())

        with pytest.raises(NotFoundError):
            owned_or_404(resource, actor(), message=MESSAGE)

    def test_an_investor_is_refused(self) -> None:
        """Investors reach startups through the summary tier (T4.2), not here."""
        resource = Owned(owner_id=uuid.uuid4())

        with pytest.raises(NotFoundError):
            owned_or_404(resource, actor(role=Role.INVESTOR), message=MESSAGE)

    def test_a_missing_row_is_refused(self) -> None:
        with pytest.raises(NotFoundError):
            owned_or_404(None, actor(), message=MESSAGE)

    def test_an_investor_who_owns_the_row_still_gets_it(self) -> None:
        """The rule is ownership, not role. Role only ever *adds* reach."""
        caller = actor(role=Role.INVESTOR)

        resource = Owned(owner_id=caller.id)

        assert owned_or_404(resource, caller, message=MESSAGE) is resource


class TestTheTwoDenialsAreIndistinguishable:
    """A 403 on someone else's id would confirm the id exists (AUTH.md section 6)."""

    def test_same_exception_type(self) -> None:
        with pytest.raises(NotFoundError) as absent:
            owned_or_404(None, actor(), message=MESSAGE)
        with pytest.raises(NotFoundError) as forbidden:
            owned_or_404(Owned(owner_id=uuid.uuid4()), actor(), message=MESSAGE)

        assert type(absent.value) is type(forbidden.value)

    def test_same_message(self) -> None:
        with pytest.raises(NotFoundError) as absent:
            owned_or_404(None, actor(), message=MESSAGE)
        with pytest.raises(NotFoundError) as forbidden:
            owned_or_404(Owned(owner_id=uuid.uuid4()), actor(), message=MESSAGE)

        assert absent.value.message == forbidden.value.message == MESSAGE

    def test_same_wire_response(self) -> None:
        """Status code and error code are what the client actually compares."""
        with pytest.raises(NotFoundError) as absent:
            owned_or_404(None, actor(), message=MESSAGE)
        with pytest.raises(NotFoundError) as forbidden:
            owned_or_404(Owned(owner_id=uuid.uuid4()), actor(), message=MESSAGE)

        assert absent.value.status_code == forbidden.value.status_code == 404
        assert absent.value.code == forbidden.value.code == ErrorCode.NOT_FOUND

    def test_never_raises_forbidden(self) -> None:
        """403 must not be reachable from this function by any input."""
        with pytest.raises(NotFoundError) as refusal:
            owned_or_404(Owned(owner_id=uuid.uuid4()), actor(), message=MESSAGE)

        assert not isinstance(refusal.value, ForbiddenError)


class TestAdmin:
    def test_an_admin_reads_any_row(self) -> None:
        """SACI sees everything (AUTH.md section 2), with MFA."""
        resource = Owned(owner_id=uuid.uuid4())

        assert owned_or_404(resource, actor(role=Role.ADMIN), message=MESSAGE) is (
            resource
        )

    def test_an_unenrolled_admin_is_refused(self) -> None:
        """Cross-tenant reads still require MFA (AUTH.md section 9)."""
        resource = Owned(owner_id=uuid.uuid4())

        with pytest.raises(ForbiddenError):
            owned_or_404(
                resource,
                actor(role=Role.ADMIN, mfa_enabled=False),
                message=MESSAGE,
            )

    def test_an_admin_still_gets_404_for_a_row_that_is_not_there(self) -> None:
        """Exempt from ownership, not from existence."""
        with pytest.raises(NotFoundError):
            owned_or_404(None, actor(role=Role.ADMIN), message=MESSAGE)


class TestTheRefusalLogLeaksNothing:
    """The log stream is a lower-trust store than the database it describes."""

    def test_no_identifiers_are_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        caller = actor()
        resource = Owned(owner_id=uuid.uuid4())

        with (
            caplog.at_level(logging.INFO, logger="app.core.ownership"),
            pytest.raises(NotFoundError),
        ):
            owned_or_404(resource, caller, message=MESSAGE)

        assert caplog.records, "a refused cross-tenant read must be logged"
        logged = " ".join(
            f"{record.getMessage()} {getattr(record, 'context', '')}"
            for record in caplog.records
        )
        assert str(caller.id) not in logged
        assert str(resource.owner_id) not in logged

    def test_the_role_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Enough to spot a pattern of attempts without naming anyone."""
        with (
            caplog.at_level(logging.INFO, logger="app.core.ownership"),
            pytest.raises(NotFoundError),
        ):
            owned_or_404(Owned(owner_id=uuid.uuid4()), actor(), message=MESSAGE)

        context = getattr(caplog.records[0], "context", {})
        assert context == {"actor_role": Role.FOUNDER.value}

    def test_a_permitted_read_is_not_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caller = actor()

        with caplog.at_level(logging.INFO, logger="app.core.ownership"):
            owned_or_404(Owned(owner_id=caller.id), caller, message=MESSAGE)

        assert not caplog.records


class TestIntakeUsesTheSharedCheck:
    """The wall is one implementation, not one per module."""

    def test_intake_calls_the_shared_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Substituted, not just compared: a local copy of the rule would pass
        any assertion about the message alone."""
        from app.modules.intake import service

        seen: list[str] = []

        def spy(resource: object, caller: CurrentUser, *, message: str) -> object:
            seen.append(message)
            raise NotFoundError(message)

        monkeypatch.setattr(service, "owned_or_404", spy)

        with pytest.raises(NotFoundError):
            service._authorise(Owned(owner_id=uuid.uuid4()), actor())  # type: ignore[arg-type]

        assert seen == [service._DENIED], "intake did not route through the helper"
