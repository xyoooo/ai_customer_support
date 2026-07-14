from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from packages.config.settings import Settings
from packages.security.tokens import (
    TokenError,
    constant_time_hash_matches,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    parse_refresh_token,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        jwt_secret="unit-test-secret-with-at-least-thirty-two-characters",
    )


def test_access_token_round_trip(settings: Settings) -> None:
    user_id = uuid4()
    token = create_access_token(user_id, settings)
    claims = decode_access_token(token, settings)
    assert claims.sub == user_id
    assert claims.token_type == "access"


def test_expired_access_token_is_rejected(settings: Settings) -> None:
    token = create_access_token(
        uuid4(),
        settings,
        now=datetime.now(UTC) - timedelta(hours=1),
    )
    with pytest.raises(TokenError, match="invalid access token"):
        decode_access_token(token, settings)


def test_tampered_access_token_is_rejected(settings: Settings) -> None:
    token = create_access_token(uuid4(), settings)
    header, payload, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    tampered_token = f"{header}.{payload}.{replacement}{signature[1:]}"
    with pytest.raises(TokenError):
        decode_access_token(tampered_token, settings)


def test_refresh_token_round_trip() -> None:
    session_id = uuid4()
    raw_token, token_hash = create_refresh_token(session_id)
    parts = parse_refresh_token(raw_token)
    assert parts.session_id == session_id
    assert constant_time_hash_matches(parts.secret, token_hash)
    assert not constant_time_hash_matches(f"{parts.secret}x", token_hash)


@pytest.mark.parametrize("raw_token", ["", "not-a-token", "not-a-uuid.secret", f"{uuid4()}.short"])
def test_malformed_refresh_tokens_are_rejected(raw_token: str) -> None:
    with pytest.raises(TokenError):
        parse_refresh_token(raw_token)
