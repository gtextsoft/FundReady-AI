"""Document uploads: who may reach a file, and what may become one (T1.5).

A founder's deck, financial model, and cap table are the most sensitive things
this platform holds -- more so than the profile, because they are the raw
source rather than the summary. Two properties matter here and are asserted
against real rows:

* **every path through documents runs `owned_or_404` first.** The download
  endpoint is the sharpest case: what it returns is a bearer credential for one
  object, valid for its whole TTL with no further authentication, so signing
  one without an ownership check would leak financials past the end of the
  request that caused it.
* **nothing the client says about a file is taken as true.** The declared type
  is pinned into the signature but proves nothing; the real size and type are
  read back from storage, and what fails is deleted rather than left in the
  bucket.

Storage is faked -- R2 is not provisioned (`TASKS.md` T1.5). The database is
real. `tests/unit/test_storage.py` covers the signing itself.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import InvalidRequestError, NotFoundError
from app.core.security import AccountStatus, CurrentUser, Role
from app.modules.identity import service as identity
from app.modules.identity.models import User
from app.modules.intake import service
from app.modules.intake.documents import (
    MAX_UPLOAD_BYTES,
    DocumentKind,
    DocumentStatus,
    ScanStatus,
)
from app.modules.intake.repository import DocumentRepository
from tests.conftest import requires_database

pytestmark = [pytest.mark.security, pytest.mark.integration, requires_database]

PASSWORD = "correct-horse-battery-staple"
PDF = "application/pdf"


@dataclass
class FakeObject:
    size_bytes: int
    content_type: str


class FakeStorage:
    """Stands in for R2. Records what the service asked it to do."""

    def __init__(self) -> None:
        self.objects: dict[str, FakeObject] = {}
        self.deleted: list[str] = []
        self.signed_uploads: list[tuple[str, str]] = []
        self.signed_downloads: list[tuple[str, str | None]] = []

    def upload_url(self, key: str, *, content_type: str) -> str:
        self.signed_uploads.append((key, content_type))
        return f"https://storage.test/{key}?sig=upload"

    def download_url(self, key: str, *, filename: str | None = None) -> str:
        self.signed_downloads.append((key, filename))
        return f"https://storage.test/{key}?sig=download"

    def head(self, key: str) -> FakeObject | None:
        return self.objects.get(key)

    def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.objects.pop(key, None)

    def arrive(self, key: str, *, size: int = 2048, content_type: str = PDF) -> None:
        """Pretend the client's PUT succeeded."""
        self.objects[key] = FakeObject(size_bytes=size, content_type=content_type)


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> FakeStorage:
    fake = FakeStorage()
    monkeypatch.setattr(service, "signed_upload_url", fake.upload_url)
    monkeypatch.setattr(service, "signed_download_url", fake.download_url)
    monkeypatch.setattr(service, "head_object", fake.head)
    monkeypatch.setattr(service, "delete_object", fake.delete)
    return fake


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-signing-key-at-least-32-characters")
    monkeypatch.setenv("ARGON2_MEMORY_COST_KIB", "8192")
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def actor_for(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        role=user.role,
        status=AccountStatus.ACTIVE,
        email_verified=True,
    )


async def founder_with_profile(
    session: AsyncSession, role: Role = Role.FOUNDER
) -> tuple[CurrentUser, uuid.UUID]:
    user = await identity.register_user(
        session,
        email=f"founder-{uuid.uuid4().hex}@kanmi-logistics.com",
        password=PASSWORD,
        role=Role.FOUNDER,
        first_name="Ada",
        last_name="Tester",
    )
    assert user is not None
    user.role = role
    user.status = AccountStatus.ACTIVE
    user.email_verified_at = datetime.now(UTC)
    await session.flush()
    actor = actor_for(user)
    profile = await service.create_profile(session, actor, {"name": "Kanmi"})
    return actor, profile.id


async def uploaded(
    session: AsyncSession,
    storage: FakeStorage,
    actor: CurrentUser,
    startup_id: uuid.UUID,
) -> uuid.UUID:
    """A document taken all the way to `ready`."""
    document, _ = await service.request_upload(
        session,
        actor,
        startup_id,
        kind=DocumentKind.DECK,
        filename="deck.pdf",
        content_type=PDF,
    )
    storage.arrive(document.storage_key)
    await service.complete_upload(session, actor, document.id)
    return document.id


class TestOwnershipOnEveryPath:
    async def test_another_founder_cannot_start_an_upload(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        _, victim_startup = await founder_with_profile(db_session)
        attacker, _ = await founder_with_profile(db_session)

        with pytest.raises(NotFoundError):
            await service.request_upload(
                db_session,
                attacker,
                victim_startup,
                kind=DocumentKind.DECK,
                filename="theirs.pdf",
                content_type=PDF,
            )

        assert storage.signed_uploads == [], "no URL may be minted on a refusal"

    async def test_another_founder_cannot_download(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        """The sharpest case: the URL outlives the request that returned it."""
        owner, startup = await founder_with_profile(db_session)
        document_id = await uploaded(db_session, storage, owner, startup)
        attacker, _ = await founder_with_profile(db_session)
        storage.signed_downloads.clear()

        with pytest.raises(NotFoundError):
            await service.request_download(db_session, attacker, document_id)

        assert storage.signed_downloads == [], "no URL may be minted on a refusal"

    async def test_another_founder_cannot_complete(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        owner, startup = await founder_with_profile(db_session)
        document, _ = await service.request_upload(
            db_session,
            owner,
            startup,
            kind=DocumentKind.DECK,
            filename="deck.pdf",
            content_type=PDF,
        )
        storage.arrive(document.storage_key)
        attacker, _ = await founder_with_profile(db_session)

        with pytest.raises(NotFoundError):
            await service.complete_upload(db_session, attacker, document.id)

    async def test_another_founder_cannot_list(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        owner, startup = await founder_with_profile(db_session)
        await uploaded(db_session, storage, owner, startup)
        attacker, _ = await founder_with_profile(db_session)

        with pytest.raises(NotFoundError):
            await service.list_documents(db_session, attacker, startup)

    async def test_a_missing_document_reads_like_someone_elses(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        """403 on a real id would confirm it exists (AUTH.md section 6)."""
        owner, startup = await founder_with_profile(db_session)
        document_id = await uploaded(db_session, storage, owner, startup)
        attacker, _ = await founder_with_profile(db_session)

        with pytest.raises(NotFoundError) as real:
            await service.request_download(db_session, attacker, document_id)
        with pytest.raises(NotFoundError) as imaginary:
            await service.request_download(db_session, attacker, uuid.uuid4())

        assert real.value.message == imaginary.value.message

    async def test_the_owner_gets_their_own_document(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        owner, startup = await founder_with_profile(db_session)
        document_id = await uploaded(db_session, storage, owner, startup)

        url = await service.request_download(db_session, owner, document_id)

        assert url.startswith("https://storage.test/")

    async def test_an_admin_can_reach_any_document(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        """SACI sees everything (AUTH.md section 2)."""
        owner, startup = await founder_with_profile(db_session)
        document_id = await uploaded(db_session, storage, owner, startup)
        admin, _ = await founder_with_profile(db_session, role=Role.ADMIN)

        url = await service.request_download(db_session, admin, document_id)

        assert url


class TestTheKeyIsNeverClientControlled:
    async def test_the_filename_is_not_part_of_the_key(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        actor, startup = await founder_with_profile(db_session)

        document, _ = await service.request_upload(
            db_session,
            actor,
            startup,
            kind=DocumentKind.DECK,
            filename="../../../etc/passwd",
            content_type=PDF,
        )

        assert document.storage_key == f"{startup}/{document.id}"
        assert ".." not in document.storage_key
        assert "passwd" not in document.storage_key

    async def test_a_traversing_filename_is_stored_flattened(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        """It is echoed back and set as a download header, so it is cleaned."""
        actor, startup = await founder_with_profile(db_session)

        document, _ = await service.request_upload(
            db_session,
            actor,
            startup,
            kind=DocumentKind.DECK,
            filename="../../secrets/deck.pdf",
            content_type=PDF,
        )

        assert document.filename == "deck.pdf"

    async def test_a_windows_path_is_flattened_too(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        actor, startup = await founder_with_profile(db_session)

        document, _ = await service.request_upload(
            db_session,
            actor,
            startup,
            kind=DocumentKind.DECK,
            filename=r"C:\Users\founder\deck.pdf",
            content_type=PDF,
        )

        assert document.filename == "deck.pdf"

    async def test_an_empty_filename_still_yields_something(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        actor, startup = await founder_with_profile(db_session)

        document, _ = await service.request_upload(
            db_session,
            actor,
            startup,
            kind=DocumentKind.DECK,
            filename="...",
            content_type=PDF,
        )

        assert document.filename == "upload"


class TestWhatMayBecomeADocument:
    async def test_an_unsupported_type_is_refused_up_front(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        actor, startup = await founder_with_profile(db_session)

        with pytest.raises(InvalidRequestError):
            await service.request_upload(
                db_session,
                actor,
                startup,
                kind=DocumentKind.OTHER,
                filename="run.exe",
                content_type="application/x-msdownload",
            )

        assert storage.signed_uploads == []

    async def test_a_charset_parameter_does_not_break_a_valid_type(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        """Browsers send `text/csv; charset=utf-8`."""
        actor, startup = await founder_with_profile(db_session)

        document, _ = await service.request_upload(
            db_session,
            actor,
            startup,
            kind=DocumentKind.FINANCIALS,
            filename="model.csv",
            content_type="text/csv; charset=utf-8",
        )

        assert document.status is DocumentStatus.PENDING

    async def test_an_oversized_upload_is_rejected_and_deleted(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        """Size cannot be constrained by a presigned PUT, so it is checked
        after the fact -- and what fails does not stay in the bucket."""
        actor, startup = await founder_with_profile(db_session)
        document, _ = await service.request_upload(
            db_session,
            actor,
            startup,
            kind=DocumentKind.DECK,
            filename="huge.pdf",
            content_type=PDF,
        )
        storage.arrive(document.storage_key, size=MAX_UPLOAD_BYTES + 1)

        with pytest.raises(InvalidRequestError):
            await service.complete_upload(db_session, actor, document.id)

        assert document.storage_key in storage.deleted
        assert document.status is DocumentStatus.REJECTED

    async def test_an_empty_upload_is_rejected(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        actor, startup = await founder_with_profile(db_session)
        document, _ = await service.request_upload(
            db_session,
            actor,
            startup,
            kind=DocumentKind.DECK,
            filename="empty.pdf",
            content_type=PDF,
        )
        storage.arrive(document.storage_key, size=0)

        with pytest.raises(InvalidRequestError):
            await service.complete_upload(db_session, actor, document.id)

        assert document.status is DocumentStatus.REJECTED

    async def test_a_type_switched_after_signing_is_caught(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        """The declared type is checked again against what actually landed."""
        actor, startup = await founder_with_profile(db_session)
        document, _ = await service.request_upload(
            db_session,
            actor,
            startup,
            kind=DocumentKind.DECK,
            filename="deck.pdf",
            content_type=PDF,
        )
        storage.arrive(document.storage_key, content_type="application/x-msdownload")

        with pytest.raises(InvalidRequestError):
            await service.complete_upload(db_session, actor, document.id)

        assert document.storage_key in storage.deleted

    async def test_completing_before_the_file_arrives_is_refused(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        actor, startup = await founder_with_profile(db_session)
        document, _ = await service.request_upload(
            db_session,
            actor,
            startup,
            kind=DocumentKind.DECK,
            filename="deck.pdf",
            content_type=PDF,
        )

        with pytest.raises(InvalidRequestError):
            await service.complete_upload(db_session, actor, document.id)

        assert document.status is DocumentStatus.PENDING

    async def test_size_and_type_come_from_storage_not_the_client(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        actor, startup = await founder_with_profile(db_session)
        document, _ = await service.request_upload(
            db_session,
            actor,
            startup,
            kind=DocumentKind.DECK,
            filename="deck.pdf",
            content_type=PDF,
        )
        storage.arrive(document.storage_key, size=4096, content_type=PDF)

        completed = await service.complete_upload(db_session, actor, document.id)

        assert completed.size_bytes == 4096
        assert completed.content_type == PDF


class TestDownloadGating:
    async def test_a_pending_document_cannot_be_downloaded(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        actor, startup = await founder_with_profile(db_session)
        document, _ = await service.request_upload(
            db_session,
            actor,
            startup,
            kind=DocumentKind.DECK,
            filename="deck.pdf",
            content_type=PDF,
        )

        with pytest.raises(InvalidRequestError):
            await service.request_download(db_session, actor, document.id)

        assert storage.signed_downloads == []

    async def test_an_infected_document_cannot_be_downloaded(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        """No scanner is wired yet, but the gate it will use must hold."""
        actor, startup = await founder_with_profile(db_session)
        document_id = await uploaded(db_session, storage, actor, startup)
        document = await DocumentRepository(db_session).get(document_id)
        assert document is not None
        document.scan_status = ScanStatus.INFECTED
        await db_session.flush()
        storage.signed_downloads.clear()

        with pytest.raises(InvalidRequestError):
            await service.request_download(db_session, actor, document_id)

        assert storage.signed_downloads == []


class TestUploadLifecycle:
    async def test_completing_twice_is_safe(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        """A client that retries after a dropped response must not re-enter."""
        actor, startup = await founder_with_profile(db_session)
        document_id = await uploaded(db_session, storage, actor, startup)

        again = await service.complete_upload(db_session, actor, document_id)

        assert again.status is DocumentStatus.READY
        assert storage.deleted == []

    async def test_an_unscanned_file_is_never_recorded_clean(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        """`skipped` is the honest answer until T5.5 wires a scanner."""
        actor, startup = await founder_with_profile(db_session)
        document_id = await uploaded(db_session, storage, actor, startup)

        document = await DocumentRepository(db_session).get(document_id)

        assert document is not None
        assert document.scan_status is ScanStatus.SKIPPED
        assert document.scan_status is not ScanStatus.CLEAN

    async def test_documents_are_listed_for_their_own_startup_only(
        self, db_session: AsyncSession, storage: FakeStorage
    ) -> None:
        owner, startup = await founder_with_profile(db_session)
        await uploaded(db_session, storage, owner, startup)
        other, other_startup = await founder_with_profile(db_session)
        await uploaded(db_session, storage, other, other_startup)

        mine = await service.list_documents(db_session, owner, startup)

        assert len(mine) == 1
        assert all(document.startup_id == startup for document in mine)
