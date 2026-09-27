"""Auth request/response schemas."""

from uuid import UUID

from pydantic import EmailStr, Field

from app.db.models import UserRole
from app.schemas.common import ApiModel


class UserCreate(ApiModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=255)
    # Accepted for backward compatibility; anything other than "ta" is rejected.
    role: UserRole = UserRole.TA


class UserLogin(ApiModel):
    email: EmailStr
    password: str


class PasswordChange(ApiModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserResponse(ApiModel):
    id: UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool = True

    model_config = {"from_attributes": True}


class TokenResponse(ApiModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class AuthStatusResponse(ApiModel):
    auth_enabled: bool
    allow_self_registration: bool | None = None
    message: str | None = None
