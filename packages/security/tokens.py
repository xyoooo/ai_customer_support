from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

import jwt
from pydantic import BaseModel, ValidationError

from packages.config.settings import Settings


class AccessTokenClaims(BaseModel):
    sub: UUID
    iss: str
    aud: str
    iat: datetime
    exp: datetime
    jti: UUID
    token_type: str


class TokenError(ValueError):
    pass


@dataclass(frozen=True)
class RefreshTokenParts:
    session_id: UUID
    secret: str


def create_access_token(user_id: UUID, settings: Settings, *, now: datetime | None = None) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=settings.access_token_minutes),
        "jti": str(uuid4()),
        "token_type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str, settings: Settings) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "iss", "aud", "iat", "exp", "jti", "token_type"]},
        )
        claims = AccessTokenClaims.model_validate(payload)
    except (jwt.PyJWTError, ValidationError, ValueError) as exc:
        raise TokenError("invalid access token") from exc
    if claims.token_type != "access":  # noqa: S105 - claim discriminator, not a credential
        raise TokenError("invalid token type")
    return claims


def create_refresh_token(session_id: UUID) -> tuple[str, str]:
    secret = secrets.token_urlsafe(32)
    return f"{session_id}.{secret}", hash_refresh_secret(secret)


def parse_refresh_token(raw_token: str) -> RefreshTokenParts:
    try:
        raw_session_id, secret = raw_token.split(".", maxsplit=1)
        session_id = UUID(raw_session_id)
    except (ValueError, AttributeError) as exc:
        raise TokenError("invalid refresh token") from exc
    if len(secret) < 32:
        raise TokenError("invalid refresh token")
    return RefreshTokenParts(session_id=session_id, secret=secret)


def hash_refresh_secret(secret: str) -> str:
    return sha256(secret.encode("utf-8")).hexdigest()


def constant_time_hash_matches(secret: str, expected_hash: str) -> bool:
    return secrets.compare_digest(hash_refresh_secret(secret), expected_hash)
