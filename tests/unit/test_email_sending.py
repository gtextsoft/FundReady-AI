"""Transactional email, driven without a network.

The properties worth protecting here are not "does it call the API" but the two
that fail quietly: a send failure must not propagate into the caller, and the
recipient's address must never reach a log line.
"""

import json
import logging
from collections.abc import Iterator

import httpx
import pytest

from app.core.config import get_settings
from app.modules.notifications import service
from app.modules.notifications.templates import (
    password_reset_email,
    verification_email,
)

RECIPIENT = "founder@example.test"
LINK = "https://api.fundready.test/v1/auth/verify-email?token=abc123"


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key_value")
    monkeypatch.setenv("EMAIL_FROM_ADDRESS", "no-reply@fundready.test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def responder(
    status: int = 200, capture: list[httpx.Request] | None = None
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        # A real provider error quotes the address back; this stands in for it.
        body = {"id": "msg_1"} if status < 400 else {"message": f"invalid: {RECIPIENT}"}
        return httpx.Response(status, json=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestSending:
    async def test_posts_to_resend(self, configured: None) -> None:
        requests: list[httpx.Request] = []
        async with responder(capture=requests) as client:
            sent = await service.send_email(
                RECIPIENT, verification_email(LINK), client=client
            )

        assert sent is True
        assert len(requests) == 1
        assert str(requests[0].url) == service.RESEND_ENDPOINT

    async def test_sends_the_expected_payload(self, configured: None) -> None:
        requests: list[httpx.Request] = []
        async with responder(capture=requests) as client:
            await service.send_email(RECIPIENT, verification_email(LINK), client=client)

        body = json.loads(requests[0].content)
        assert body["to"] == [RECIPIENT]
        assert body["from"] == "no-reply@fundready.test"
        assert LINK in body["html"]
        assert LINK in body["text"], "plain text is not optional"
        assert requests[0].headers["authorization"] == "Bearer re_test_key_value"


class TestFailuresAreContained:
    @pytest.mark.parametrize("status", [400, 401, 422, 429, 500, 503])
    async def test_provider_errors_do_not_raise(
        self, configured: None, status: int
    ) -> None:
        """A caller must never fail because email is down."""
        async with responder(status=status) as client:
            sent = await service.send_email(
                RECIPIENT, verification_email(LINK), client=client
            )

        assert sent is False

    async def test_network_errors_do_not_raise(self, configured: None) -> None:
        def explode(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("provider unreachable", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(explode)) as client:
            sent = await service.send_email(
                RECIPIENT, verification_email(LINK), client=client
            )

        assert sent is False

    async def test_unconfigured_makes_no_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        requests: list[httpx.Request] = []
        get_settings.cache_clear()

        async with responder(capture=requests) as client:
            sent = await service.send_email(
                RECIPIENT, verification_email(LINK), client=client
            )

        assert sent is False
        assert requests == [], "no key means no call, not a call that fails"


class TestNoRecipientInLogs:
    """An email address is PII (CLAUDE.md section 4)."""

    async def test_absent_on_provider_error(
        self, configured: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG):
            async with responder(status=422) as client:
                await service.send_email(
                    RECIPIENT, verification_email(LINK), client=client
                )

        assert RECIPIENT not in caplog.text
        assert "email rejected by provider" in caplog.text

    async def test_absent_on_network_error(
        self, configured: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        def explode(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError(f"failed sending to {RECIPIENT}", request=request)

        with caplog.at_level(logging.DEBUG):
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(explode)
            ) as client:
                await service.send_email(
                    RECIPIENT, verification_email(LINK), client=client
                )

        assert RECIPIENT not in caplog.text

    async def test_absent_on_success(
        self, configured: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG):
            async with responder() as client:
                await service.send_email(
                    RECIPIENT, verification_email(LINK), client=client
                )

        assert RECIPIENT not in caplog.text

    async def test_absent_when_unconfigured(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Development logs the link so flows can be completed -- not the address."""
        get_settings.cache_clear()

        with caplog.at_level(logging.DEBUG):
            await service.send_email(RECIPIENT, verification_email(LINK))

        assert RECIPIENT not in caplog.text
        assert LINK in caplog.text


class TestTemplates:
    def test_verification_carries_the_link_in_both_parts(self) -> None:
        content = verification_email(LINK)

        assert LINK in content.html
        assert LINK in content.text
        assert content.subject

    def test_reset_carries_the_link_in_both_parts(self) -> None:
        content = password_reset_email(LINK)

        assert LINK in content.html
        assert LINK in content.text

    def test_reset_states_the_no_action_case(self) -> None:
        """Someone who did not ask for this must be told to do nothing."""
        content = password_reset_email(LINK)

        assert "did not ask" in content.text
        assert "unchanged" in content.text

    @pytest.mark.parametrize(
        "content",
        [verification_email(LINK), password_reset_email(LINK)],
        ids=["verification", "reset"],
    )
    def test_templates_never_embed_a_recipient(self, content: object) -> None:
        """Templates take a link and nothing else, so they cannot leak identity."""
        rendered = f"{content}"

        assert RECIPIENT not in rendered
