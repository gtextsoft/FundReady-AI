"""Signed URLs and object keys (T1.5).

Signing is offline -- `generate_presigned_url` computes an HMAC over a request
description and never calls out -- so everything here runs against dummy
credentials with no bucket in existence. That is the only reason T1.5 has real
coverage before R2 is provisioned, and it is genuine coverage: the key layout,
the TTL, and the pinned content type are exactly what R2 will validate.

What these tests cannot prove is that R2 accepts the result. Nothing here
touches the network (see `TASKS.md` T1.5 -- the storage half is unverified).
"""

import uuid
from collections.abc import Iterator
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from app.core import storage
from app.core.config import get_settings
from app.core.errors import ConfigurationError

ENDPOINT = "https://account123.r2.cloudflarestorage.com"


@pytest.fixture(autouse=True)
def storage_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("R2_ACCOUNT_ID", "account123")
    monkeypatch.setenv("R2_ENDPOINT_URL", ENDPOINT)
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "dummy-access-key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "dummy-secret-key")
    monkeypatch.setenv("R2_BUCKET_DOCUMENTS", "fundready-documents")
    monkeypatch.setenv("R2_BUCKET_EVIDENCE", "fundready-evidence")
    monkeypatch.setenv("STORAGE_SIGNED_URL_TTL_SECONDS", "900")
    get_settings.cache_clear()
    storage.reset_client_cache()
    yield
    get_settings.cache_clear()
    storage.reset_client_cache()


def query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


class TestObjectKey:
    def test_both_components_are_the_ids_we_generated(self) -> None:
        startup, document = uuid.uuid4(), uuid.uuid4()

        assert storage.object_key(startup, document) == f"{startup}/{document}"

    def test_keys_are_unique_per_document(self) -> None:
        startup = uuid.uuid4()

        first = storage.object_key(startup, uuid.uuid4())
        second = storage.object_key(startup, uuid.uuid4())

        assert first != second

    def test_two_startups_cannot_collide(self) -> None:
        """The prefix is the startup, so one founder's tree is its own."""
        document = uuid.uuid4()

        first = storage.object_key(uuid.uuid4(), document)
        second = storage.object_key(uuid.uuid4(), document)

        assert first != second


class TestSignedUploadUrl:
    def test_it_points_at_the_documents_bucket_and_key(self) -> None:
        key = storage.object_key(uuid.uuid4(), uuid.uuid4())

        url = storage.signed_upload_url(key, content_type="application/pdf")

        assert url.startswith(ENDPOINT)
        assert f"/fundready-documents/{key}" in unquote(urlparse(url).path)

    def test_it_is_signed_and_expires(self) -> None:
        url = storage.signed_upload_url("a/b", content_type="application/pdf")

        parameters = query(url)
        assert parameters["X-Amz-Expires"] == ["900"]
        assert "X-Amz-Signature" in parameters
        assert "X-Amz-Credential" in parameters

    def test_the_content_type_is_part_of_the_signature(self) -> None:
        """So an upload declaring something else is refused by storage."""
        url = storage.signed_upload_url("a/b", content_type="application/pdf")

        signed_headers = query(url)["X-Amz-SignedHeaders"][0]

        assert "content-type" in signed_headers

    def test_a_different_content_type_signs_differently(self) -> None:
        pdf = storage.signed_upload_url("a/b", content_type="application/pdf")
        png = storage.signed_upload_url("a/b", content_type="image/png")

        assert query(pdf)["X-Amz-Signature"] != query(png)["X-Amz-Signature"]

    def test_the_secret_key_never_appears_in_the_url(self) -> None:
        url = storage.signed_upload_url("a/b", content_type="application/pdf")

        assert "dummy-secret-key" not in url


class TestSignedDownloadUrl:
    def test_it_reads_the_same_key(self) -> None:
        key = storage.object_key(uuid.uuid4(), uuid.uuid4())

        url = storage.signed_download_url(key)

        assert f"/fundready-documents/{key}" in unquote(urlparse(url).path)

    def test_the_filename_is_offered_for_the_download(self) -> None:
        url = storage.signed_download_url("a/b", filename="kanmi-deck.pdf")

        disposition = query(url)["response-content-disposition"][0]

        assert disposition == 'attachment; filename="kanmi-deck.pdf"'

    def test_a_hostile_filename_cannot_break_the_header(self) -> None:
        """A raw quote or newline here would be header injection."""
        url = storage.signed_download_url(
            "a/b", filename='evil".pdf\r\nX-Injected: yes'
        )

        disposition = query(url)["response-content-disposition"][0]

        assert "\r" not in disposition
        assert "\n" not in disposition
        assert disposition.count('"') == 2

    def test_it_expires(self) -> None:
        url = storage.signed_download_url("a/b")

        assert query(url)["X-Amz-Expires"] == ["900"]


class TestBuckets:
    def test_documents_and_evidence_are_separate(self) -> None:
        assert storage.bucket_name("documents") != storage.bucket_name("evidence")

    def test_evidence_can_be_addressed(self) -> None:
        """T3.5 uploads evidence; the adapter already knows where."""
        url = storage.signed_upload_url(
            "a/b", content_type="application/pdf", bucket="evidence"
        )

        assert "/fundready-evidence/" in unquote(urlparse(url).path)


class TestUnconfiguredStorage:
    """A URL signed against a blank endpoint looks fine until an upload
    vanishes. Fail loudly instead."""

    def test_no_credentials_is_an_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
        get_settings.cache_clear()
        storage.reset_client_cache()

        with pytest.raises(ConfigurationError):
            storage.get_client()

    def test_no_endpoint_is_an_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("R2_ENDPOINT_URL", "")
        get_settings.cache_clear()
        storage.reset_client_cache()

        with pytest.raises(ConfigurationError):
            storage.get_client()

    def test_no_bucket_is_an_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("R2_BUCKET_DOCUMENTS", "")
        get_settings.cache_clear()

        with pytest.raises(ConfigurationError):
            storage.bucket_name("documents")
