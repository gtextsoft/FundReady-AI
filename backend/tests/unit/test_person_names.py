"""Name validation on registration.

Schema-level, so no database is needed. The rule these tests exist to protect
is the *absence* of an alphabet restriction: this platform registers people in
Nigeria, the UAE, the UK, the US, and China, and a `[A-Za-z]`-style filter
silently rejects a large share of real names. Each accepted case below is a
name someone actually has.
"""

import pytest
from pydantic import ValidationError

from app.modules.identity.schemas import RegisterRequest, Role, UserResponse

PASSWORD = "correct-horse-battery-staple"


def _payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "email": "founder@company.com",
        "password": PASSWORD,
        "role": "founder",
        "first_name": "Amaka",
        "last_name": "Okonkwo",
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# Required for both self-service roles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["founder", "investor"])
def test_both_roles_must_supply_a_name(role: str) -> None:
    request = RegisterRequest.model_validate(_payload(role=role))

    assert request.first_name == "Amaka"
    assert request.last_name == "Okonkwo"
    assert request.role is (Role.FOUNDER if role == "founder" else Role.INVESTOR)


@pytest.mark.parametrize("missing", ["first_name", "last_name"])
def test_a_missing_name_is_rejected(missing: str) -> None:
    body = _payload()
    del body[missing]

    with pytest.raises(ValidationError, match=missing):
        RegisterRequest.model_validate(body)


@pytest.mark.parametrize("blank", ["", "   ", "\t\n "])
def test_a_blank_name_is_rejected(blank: str) -> None:
    """Whitespace is stripped first, so this fails as blank rather than passing."""
    with pytest.raises(ValidationError, match="first_name"):
        RegisterRequest.model_validate(_payload(first_name=blank))


# ---------------------------------------------------------------------------
# No alphabet restriction -- these are all real names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Chidi",  # Igbo
        "Ngozi-Ann",  # hyphenated
        "O'Brien",  # apostrophe
        "van der Berg",  # spaces and lowercase particles
        "Zoë",  # diacritic
        "Björk",  # diacritic
        "李",  # Han, single character
        "محمد",  # Arabic
        "Ọláwálé",  # Yoruba with tone marks
        "J",  # a single letter is a legitimate name
    ],
)
def test_real_names_are_accepted(name: str) -> None:
    request = RegisterRequest.model_validate(_payload(first_name=name))

    assert request.first_name == name


def test_surrounding_whitespace_is_trimmed() -> None:
    request = RegisterRequest.model_validate(_payload(first_name="  Amaka  "))

    assert request.first_name == "Amaka"


def test_internal_spacing_is_preserved() -> None:
    """`van der Berg` is not `vanderBerg`."""
    request = RegisterRequest.model_validate(_payload(last_name="van der Berg"))

    assert request.last_name == "van der Berg"


# ---------------------------------------------------------------------------
# Bounds and control characters
# ---------------------------------------------------------------------------


def test_control_characters_are_stripped() -> None:
    request = RegisterRequest.model_validate(_payload(first_name="Am\x00ak\x1ba"))

    assert request.first_name == "Amaka"


def test_a_name_at_the_limit_is_accepted() -> None:
    request = RegisterRequest.model_validate(_payload(first_name="A" * 100))

    assert len(request.first_name) == 100


def test_an_overlong_name_is_rejected() -> None:
    with pytest.raises(ValidationError, match="first_name"):
        RegisterRequest.model_validate(_payload(first_name="A" * 101))


def test_padding_is_not_counted_against_the_limit() -> None:
    """Cleaning runs before the length rule, so trailing spaces do not reject."""
    request = RegisterRequest.model_validate(_payload(first_name="A" * 100 + "     "))

    assert len(request.first_name) == 100


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


def test_the_response_carries_both_names() -> None:
    fields = UserResponse.model_fields

    assert "first_name" in fields
    assert "last_name" in fields


def test_the_response_allows_null_names() -> None:
    """Admins and pre-existing accounts never saw the registration form."""
    import uuid
    from datetime import UTC, datetime

    response = UserResponse.model_validate(
        {
            "id": uuid.uuid4(),
            "email": "admin@saci.example",
            "role": "admin",
            "first_name": None,
            "last_name": None,
            "status": "active",
            "email_verified": True,
            "kyc_status": "none",
            "subscription_status": "none",
            "created_at": datetime.now(UTC),
        }
    )

    assert response.first_name is None
