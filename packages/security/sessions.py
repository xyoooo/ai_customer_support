from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from packages.config.settings import Settings
from packages.database.models import RefreshSession, User
from packages.domain.errors import AuthenticationError
from packages.security.tokens import (
    constant_time_hash_matches,
    create_access_token,
    create_refresh_token,
    parse_refresh_token,
)


@dataclass(frozen=True)
class IssuedSession:
    access_token: str
    refresh_token: str


def utc_now() -> datetime:
    return datetime.now(UTC)


async def issue_session(
    session: AsyncSession,
    *,
    user: User,
    settings: Settings,
    user_agent: str | None,
    ip_address: str | None,
    family_id: UUID | None = None,
) -> tuple[RefreshSession, IssuedSession]:
    now = utc_now()
    refresh_session_id = uuid4()
    raw_refresh, token_hash = create_refresh_token(refresh_session_id)
    refresh_session = RefreshSession(
        id=refresh_session_id,
        user_id=user.id,
        family_id=family_id or uuid4(),
        token_hash=token_hash,
        user_agent=(user_agent or "")[:512] or None,
        ip_address=ip_address,
        created_at=now,
        expires_at=now + timedelta(days=settings.refresh_token_days),
    )
    session.add(refresh_session)
    return refresh_session, IssuedSession(
        access_token=create_access_token(user.id, settings, now=now),
        refresh_token=raw_refresh,
    )


async def rotate_session(
    session: AsyncSession,
    *,
    raw_refresh_token: str,
    settings: Settings,
    user_agent: str | None,
    ip_address: str | None,
) -> tuple[User, IssuedSession]:
    try:
        parts = parse_refresh_token(raw_refresh_token)
    except ValueError as exc:
        raise AuthenticationError("session is invalid or expired") from exc

    current = await session.scalar(
        select(RefreshSession).where(RefreshSession.id == parts.session_id).with_for_update()
    )
    if current is None or not constant_time_hash_matches(parts.secret, current.token_hash):
        raise AuthenticationError("session is invalid or expired")

    now = utc_now()
    if current.used_at is not None or current.revoked_at is not None:
        await session.execute(
            update(RefreshSession)
            .where(RefreshSession.family_id == current.family_id)
            .values(revoked_at=now)
        )
        # Persist family invalidation even though the request returns an authentication error.
        await session.commit()
        raise AuthenticationError("session reuse detected; please sign in again")
    if current.expires_at <= now:
        current.revoked_at = now
        raise AuthenticationError("session is invalid or expired")

    user = await session.get(User, current.user_id)
    if user is None or not user.is_active:
        current.revoked_at = now
        raise AuthenticationError("session is invalid or expired")

    replacement, issued = await issue_session(
        session,
        user=user,
        settings=settings,
        user_agent=user_agent,
        ip_address=ip_address,
        family_id=current.family_id,
    )
    # The replacement must exist before the old row points at it through the self-FK.
    await session.flush([replacement])
    current.used_at = now
    current.revoked_at = now
    current.replaced_by_id = replacement.id
    return user, issued


async def revoke_session(session: AsyncSession, raw_refresh_token: str) -> None:
    try:
        parts = parse_refresh_token(raw_refresh_token)
    except ValueError:
        return
    current = await session.scalar(
        select(RefreshSession).where(RefreshSession.id == parts.session_id).with_for_update()
    )
    if current is not None and constant_time_hash_matches(parts.secret, current.token_hash):
        current.revoked_at = current.revoked_at or utc_now()
