import pytest
from pydantic import ValidationError

from skillhub_api.schemas.auth import (
    LocalLoginRequest,
    LocalRegisterRequest,
    PasswordResetConfirmRequest,
    TokenCreateRequest,
)


def test_register_rejects_short_username() -> None:
    with pytest.raises(ValidationError):
        LocalRegisterRequest(username="ab", password="longenoughpw")


def test_register_rejects_short_password() -> None:
    with pytest.raises(ValidationError):
        LocalRegisterRequest(username="valid_user", password="short")


def test_register_accepts_valid_payload() -> None:
    dto = LocalRegisterRequest(
        username="valid_user",
        password="longenoughpw",
        email="user@example.com",
    )
    assert dto.username == "valid_user"
    assert dto.email == "user@example.com"


def test_login_accepts_bare_payload() -> None:
    dto = LocalLoginRequest(username="x", password="y")
    assert dto.username == "x"


def test_password_reset_code_must_be_six_digits() -> None:
    with pytest.raises(ValidationError):
        PasswordResetConfirmRequest(
            email="u@example.com", code="12345", new_password="longenoughpw"
        )


def test_token_create_defaults_empty_scope() -> None:
    dto = TokenCreateRequest(name="ci")
    assert dto.scope == []
    assert dto.expires_at is None
