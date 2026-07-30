"""Object storage: Cloudflare R2 over the S3 API (T1.5).

Files never go in Postgres (`fundready-prd.md` §7, `DECISIONS.md` D4) and never
through this API's own request path. The client uploads **straight to R2** with
a short-lived signed URL, and downloads the same way. Two reasons that matters:
a 25 MB deck streaming through a small web dyno is wasted memory and wasted
egress, and bytes we never touch are bytes we cannot accidentally log.

Layer: an **adapter** in `core`, alongside `db.py` -- infrastructure, no
business rules. It signs URLs and asks R2 about objects. Who may upload, what
counts as an acceptable file, and what happens next are decisions for
`intake.service`.

**Signing is offline.** `generate_presigned_url` computes an HMAC over the
request it describes; no call leaves the process, and R2 validates the
signature when the client presents it. So key layout and URL construction are
genuinely unit-testable against dummy credentials with no bucket in existence
-- which is the only reason T1.5 has tests at all before R2 is provisioned.

**A signed URL is a bearer token for one object.** Anyone holding it has that
access until it expires, with no further authentication. Two consequences,
both enforced by the caller rather than here: never mint one without an
ownership check first, and keep the TTL short
(`STORAGE_SIGNED_URL_TTL_SECONDS`, 15 minutes).
"""

import logging
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError

logger = logging.getLogger(__name__)

Bucket = Literal["documents", "evidence"]


@dataclass(frozen=True, slots=True)
class StoredObject:
    """What R2 reports about an object that is actually there."""

    size_bytes: int
    content_type: str


def object_key(owner_scope: uuid.UUID, object_id: uuid.UUID) -> str:
    """Where an object lives, decided entirely by us.

    Both components are UUIDs the server generated. **No part of a key ever
    comes from the client** -- not the filename, not a folder, not an
    extension. A user-supplied path component is how `../` walks out of a
    prefix, and how one founder's key collides with another's on purpose. The
    original filename is display text stored in the database column, and
    nothing more.
    """
    return f"{owner_scope}/{object_id}"


@lru_cache(maxsize=1)
def _client_for(
    endpoint: str, access_key: str, secret_key: str
) -> Any:  # botocore clients are untyped
    """Cached by credentials, because building a client parses botocore's
    bundled service model and that is slow enough to notice per request."""
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        # R2 ignores regions but the SDK insists on one; `auto` is what
        # Cloudflare documents.
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def get_client(settings: Settings | None = None) -> Any:
    """The R2 client, or `ConfigurationError` if storage is not configured.

    Fails loudly rather than returning a client that would produce URLs
    pointing nowhere: a signed URL against a blank endpoint looks plausible
    right up until a founder's upload disappears.
    """
    settings = settings or get_settings()
    access_key = settings.r2_access_key_id
    secret_key = settings.r2_secret_access_key
    if not settings.r2_endpoint_url or access_key is None or secret_key is None:
        raise ConfigurationError("Object storage is not configured.")
    return _client_for(
        settings.r2_endpoint_url,
        access_key.get_secret_value(),
        secret_key.get_secret_value(),
    )


def bucket_name(which: Bucket, settings: Settings | None = None) -> str:
    """Documents and evidence are separate buckets from the start.

    They have different lifecycles and different readers -- evidence is graded
    by a job and can be re-uploaded, documents feed extraction -- and splitting
    them later means moving objects and rewriting keys.
    """
    settings = settings or get_settings()
    name = (
        settings.r2_bucket_documents
        if which == "documents"
        else settings.r2_bucket_evidence
    )
    if not name:
        raise ConfigurationError("Object storage is not configured.")
    return name


def signed_upload_url(
    key: str,
    *,
    content_type: str,
    bucket: Bucket = "documents",
    settings: Settings | None = None,
) -> str:
    """A URL the client may `PUT` exactly one object to.

    `content_type` is part of the signature, so the client must send the same
    `Content-Type` header or R2 rejects the request. That pins what the client
    **declares**, which is not the same as what the bytes are -- an attacker
    can label a script `application/pdf` and it will upload. Real type
    checking is the caller's `complete` step and the scan hook behind it.

    Size cannot be constrained this way at all: `PUT` carries no policy
    conditions. The caller verifies the actual size with `head_object` after
    the upload lands, and deletes anything that does not qualify.
    """
    settings = settings or get_settings()
    client = get_client(settings)
    url: str = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket_name(bucket, settings),
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=settings.storage_signed_url_ttl_seconds,
    )
    return url


def signed_download_url(
    key: str,
    *,
    filename: str | None = None,
    bucket: Bucket = "documents",
    settings: Settings | None = None,
) -> str:
    """A URL that reads one object until it expires.

    `filename` sets `Content-Disposition` so the browser saves the founder's
    original name rather than a UUID. It is quoted and stripped of the
    characters that would let it break out of the header -- a raw newline here
    would be header injection on every download.
    """
    settings = settings or get_settings()
    client = get_client(settings)
    params: dict[str, str] = {
        "Bucket": bucket_name(bucket, settings),
        "Key": key,
    }
    if filename:
        safe = "".join(
            character
            for character in filename
            if character.isprintable() and character not in '"\\'
        )[:200]
        params["ResponseContentDisposition"] = f'attachment; filename="{safe}"'

    url: str = client.generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=settings.storage_signed_url_ttl_seconds,
    )
    return url


def head_object(
    key: str, *, bucket: Bucket = "documents", settings: Settings | None = None
) -> StoredObject | None:
    """What is actually stored at `key`, or `None` if nothing is.

    The only trustworthy source for an uploaded file's size and declared type:
    the client reports both, and the client is the party being checked.
    """
    settings = settings or get_settings()
    client = get_client(settings)
    try:
        response = client.head_object(Bucket=bucket_name(bucket, settings), Key=key)
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code")
        if code in ("404", "NoSuchKey", "NotFound"):
            return None
        raise
    return StoredObject(
        size_bytes=int(response.get("ContentLength", 0)),
        content_type=str(response.get("ContentType", "")),
    )


def delete_object(
    key: str, *, bucket: Bucket = "documents", settings: Settings | None = None
) -> None:
    """Remove an object. Used to clean up an upload that failed validation.

    Never raises for a key that is not there -- S3 delete is idempotent, and a
    rejected upload must be removable whether or not it ever landed.
    """
    settings = settings or get_settings()
    client = get_client(settings)
    client.delete_object(Bucket=bucket_name(bucket, settings), Key=key)


def reset_client_cache() -> None:
    """Drop cached clients. For tests, which change credentials per case."""
    _client_for.cache_clear()


__all__ = [
    "Bucket",
    "StoredObject",
    "bucket_name",
    "delete_object",
    "get_client",
    "head_object",
    "object_key",
    "reset_client_cache",
    "signed_download_url",
    "signed_upload_url",
]
