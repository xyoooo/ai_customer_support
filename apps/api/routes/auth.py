from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from apps.api.dependencies import AppSettings, CurrentPrincipal, DatabaseSession
from packages.database.models import User, Workspace, WorkspaceMembership
from packages.database.tenant import set_tenant_context
from packages.domain.enums import WorkspaceRole
from packages.domain.errors import AuthenticationError, ConflictError
from packages.domain.schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from packages.security.passwords import DUMMY_PASSWORD_HASH, hash_password, verify_password
from packages.security.sessions import issue_session, revoke_session, rotate_session

router = APIRouter(prefix="/auth", tags=["authentication"])


def client_metadata(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return user_agent, ip_address


def set_refresh_cookie(response: Response, raw_token: str, settings: AppSettings) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=raw_token,
        max_age=int(timedelta(days=settings.refresh_token_days).total_seconds()),
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/api/v1/auth",
    )


def clear_refresh_cookie(response: Response, settings: AppSettings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
        path="/api/v1/auth",
    )


def auth_response(user: User, access_token: str, settings: AppSettings) -> AuthResponse:
    return AuthResponse(
        user=UserResponse.model_validate(user),
        token=TokenResponse(
            access_token=access_token,
            expires_in=settings.access_token_minutes * 60,
        ),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: DatabaseSession,
    settings: AppSettings,
) -> AuthResponse:
    normalized_email = str(payload.email).strip().lower()
    if await session.scalar(select(User.id).where(User.email == normalized_email)):
        raise ConflictError("an account with this email already exists")

    user = User(
        id=uuid4(),
        email=normalized_email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    workspace = Workspace(
        id=uuid4(),
        name=payload.workspace_name,
        slug=payload.workspace_slug,
        created_by=user.id,
    )
    session.add(user)
    await session.flush()
    await set_tenant_context(session, user_id=user.id, workspace_id=workspace.id)
    session.add(workspace)
    session.add(
        WorkspaceMembership(
            id=uuid4(),
            workspace_id=workspace.id,
            user_id=user.id,
            role=WorkspaceRole.OWNER,
        )
    )
    user_agent, ip_address = client_metadata(request)
    _, issued = await issue_session(
        session,
        user=user,
        settings=settings,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("email or workspace slug is already in use") from exc
    set_refresh_cookie(response, issued.refresh_token, settings)
    return auth_response(user, issued.access_token, settings)


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: DatabaseSession,
    settings: AppSettings,
) -> AuthResponse:
    user = await session.scalar(
        select(User).where(User.email == str(payload.email).strip().lower())
    )
    password_matches = verify_password(
        payload.password,
        user.password_hash if user is not None else DUMMY_PASSWORD_HASH,
    )
    if user is None or not user.is_active or not password_matches:
        raise AuthenticationError("email or password is incorrect")
    user_agent, ip_address = client_metadata(request)
    _, issued = await issue_session(
        session,
        user=user,
        settings=settings,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    set_refresh_cookie(response, issued.refresh_token, settings)
    return auth_response(user, issued.access_token, settings)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    request: Request,
    response: Response,
    session: DatabaseSession,
    settings: AppSettings,
) -> AuthResponse:
    refresh_cookie = request.cookies.get(settings.refresh_cookie_name)
    if not refresh_cookie:
        raise AuthenticationError("session is invalid or expired")
    user_agent, ip_address = client_metadata(request)
    user, issued = await rotate_session(
        session,
        raw_refresh_token=refresh_cookie,
        settings=settings,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    set_refresh_cookie(response, issued.refresh_token, settings)
    return auth_response(user, issued.access_token, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: DatabaseSession,
    settings: AppSettings,
) -> None:
    refresh_cookie = request.cookies.get(settings.refresh_cookie_name)
    if refresh_cookie:
        await revoke_session(session, refresh_cookie)
    clear_refresh_cookie(response, settings)


@router.get("/me", response_model=UserResponse)
async def me(principal: CurrentPrincipal) -> User:
    return principal.user
