"""Magic-byte verification for uploads (T5.5 seam of CLAUDE.md section 4).

Not a full antivirus product — that needs an external scanner. This checks that
the declared MIME type matches the file's leading bytes so a renamed executable
cannot sit behind `application/pdf`. Infected / mismatched files are marked
`INFECTED` and refused by `_is_auditable`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MagicRule:
    content_type: str
    signatures: tuple[bytes, ...]


# Leading-byte signatures for every allowlisted type we can fingerprint.
# CSV/text and legacy OLE Office formats are handled specially below.
_RULES: tuple[MagicRule, ...] = (
    MagicRule("application/pdf", (b"%PDF",)),
    MagicRule(
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        (b"PK\x03\x04",),
    ),
    MagicRule(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        (b"PK\x03\x04",),
    ),
    MagicRule(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        (b"PK\x03\x04",),
    ),
    MagicRule("image/png", (b"\x89PNG\r\n\x1a\n",)),
    MagicRule("image/jpeg", (b"\xff\xd8\xff",)),
)

_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_OLE_TYPES = frozenset(
    {
        "application/msword",
        "application/vnd.ms-excel",
        "application/vnd.ms-powerpoint",
    }
)


def content_type_matches_bytes(content_type: str, head: bytes) -> bool:
    """Whether `head` (first ~16 bytes) is consistent with `content_type`."""
    bare = content_type.split(";")[0].strip().lower()
    if bare == "text/csv":
        # CSV has no magic; reject NUL / obvious binary.
        return b"\x00" not in head[:512]
    if bare in _OLE_TYPES:
        return head.startswith(_OLE)
    for rule in _RULES:
        if rule.content_type == bare:
            return any(head.startswith(sig) for sig in rule.signatures)
    # Unknown allowlisted type: refuse rather than mark clean.
    return False


__all__ = ["content_type_matches_bytes"]
