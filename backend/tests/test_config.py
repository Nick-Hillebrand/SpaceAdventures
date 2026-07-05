import pytest

from app.config import Settings


def test_defaults_load_without_secrets_in_dev_mode():
    settings = Settings(require_secrets=False)  # type: ignore[call-arg]
    assert settings.nasa_api_key == "DEMO_KEY"
    assert settings.nasa_base_url.startswith("https://")
    assert settings.jwt_algorithm == "HS256"
    assert settings.access_token_ttl_seconds == 900


def test_missing_secrets_raise_in_strict_mode():
    with pytest.raises(ValueError) as exc_info:
        Settings(  # type: ignore[call-arg]
            require_secrets=True,
            jwt_secret_key="",
            unsubscribe_secret_key="",
            admin_api_key="",
        )
    msg = str(exc_info.value)
    assert "JWT_SECRET_KEY" in msg
    assert "UNSUBSCRIBE_SECRET_KEY" in msg
    assert "ADMIN_API_KEY" in msg


def test_all_secrets_present_in_strict_mode():
    settings = Settings(  # type: ignore[call-arg]
        require_secrets=True,
        jwt_secret_key="j",
        unsubscribe_secret_key="u",
        admin_api_key="a",
    )
    assert settings.admin_api_key == "a"
