"""Versioned prompt templates.

A published prompt version is never edited in place -- changes ship as a new
version, and the version used is recorded on every AuditRun so past audits stay
explainable (DECISIONS.md D12).

**Why a registry rather than string constants.** "Never edit a published
version" is a rule that a plain module-level string cannot enforce: editing one
is a one-character change that leaves no trace, and the audit that cited it now
describes a prompt that no longer exists. Here a published prompt is frozen, is
looked up by `(name, version)`, and registering over an existing pair raises.
The failure mode moves from a silently rewritten history to an import-time
error telling you to bump the version.

**Recording, not just selecting.** Every call through `ai.client` carries a
`PromptVersion` and returns its `ref` (`"audit_scoring@3"`) in the call record,
so the pipeline can persist it on the AuditRun without re-deriving which prompt
it used.

Prompt *text* is not defined here -- this is the mechanism. The rubric scoring
prompt arrives with the rubric it belongs to (T2.6), extraction with T2.4.
"""

from dataclasses import dataclass
from typing import Final


class PromptRegistryError(RuntimeError):
    """A prompt was registered twice, or looked up and not found."""


@dataclass(frozen=True, slots=True)
class PromptVersion:
    """One immutable, published prompt.

    Frozen so a caller holding a reference cannot rewrite the text that an
    AuditRun has already recorded as the one it used.
    """

    name: str
    """Stable identity across versions -- e.g. `audit_scoring`."""

    version: int
    """Monotonic. A new version is a new entry; existing ones are never edited."""

    text: str
    """The prompt body. Belongs in the cached system prefix (`ai.caching`)."""

    @property
    def ref(self) -> str:
        """The form recorded on an AuditRun -- e.g. `audit_scoring@3`."""
        return f"{self.name}@{self.version}"


_REGISTRY: Final[dict[tuple[str, int], PromptVersion]] = {}


def register(prompt: PromptVersion) -> PromptVersion:
    """Publish a prompt version.

    Raises if `(name, version)` is already taken -- including when the text is
    identical, because two call sites believing they own the same version is a
    problem regardless of whether they currently agree.
    """
    key = (prompt.name, prompt.version)
    if key in _REGISTRY:
        raise PromptRegistryError(
            f"prompt {prompt.ref} is already published; "
            "bump the version instead of editing it"
        )
    _REGISTRY[key] = prompt
    return prompt


def get(name: str, version: int) -> PromptVersion:
    """Look up a published prompt, pinned to an exact version.

    There is deliberately no "latest" lookup. Re-running an audit must reproduce
    the prompt it originally used, and a caller that silently follows the newest
    version cannot do that (DECISIONS.md D12).
    """
    try:
        return _REGISTRY[(name, version)]
    except KeyError:
        raise PromptRegistryError(f"no published prompt {name}@{version}") from None


def published() -> list[str]:
    """Every published prompt ref, sorted. For diagnostics and tests."""
    return sorted(prompt.ref for prompt in _REGISTRY.values())
