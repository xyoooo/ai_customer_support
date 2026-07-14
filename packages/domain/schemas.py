from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from packages.domain.enums import WorkspaceRole


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=128)
    workspace_name: str = Field(min_length=2, max_length=120)
    workspace_slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=2, max_length=80)

    @field_validator("display_name", "workspace_name")
    @classmethod
    def strip_names(cls, value: str) -> str:
        return value.strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type, not a credential
    expires_in: int


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    display_name: str
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserResponse
    token: TokenResponse


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=2, max_length=80)


class WorkspaceUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    role: WorkspaceRole
    created_at: datetime


class MembershipCreate(BaseModel):
    email: EmailStr
    role: WorkspaceRole

    @field_validator("role")
    @classmethod
    def owner_requires_transfer_workflow(cls, value: WorkspaceRole) -> WorkspaceRole:
        if value is WorkspaceRole.OWNER:
            raise ValueError("ownership transfer is not available in Week 1")
        return value


class MembershipUpdate(BaseModel):
    role: WorkspaceRole

    @field_validator("role")
    @classmethod
    def owner_requires_transfer_workflow(cls, value: WorkspaceRole) -> WorkspaceRole:
        if value is WorkspaceRole.OWNER:
            raise ValueError("ownership transfer is not available in Week 1")
        return value


class MembershipResponse(BaseModel):
    id: UUID
    user_id: UUID
    email: EmailStr
    display_name: str
    role: WorkspaceRole
    created_at: datetime


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str | None = None
