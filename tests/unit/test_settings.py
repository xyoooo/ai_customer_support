import pytest
from pydantic import ValidationError

from packages.config.settings import Settings


def test_production_rejects_development_secret() -> None:
    with pytest.raises(ValidationError, match="strong"):
        Settings(
            environment="production",
            jwt_secret="local-development-secret-change-before-deployment",
            secure_cookies=True,
        )


def test_production_requires_secure_cookies() -> None:
    with pytest.raises(ValidationError, match="secure cookies"):
        Settings(
            environment="production",
            jwt_secret="a-production-secret-that-is-definitely-long-enough",
            secure_cookies=False,
        )
