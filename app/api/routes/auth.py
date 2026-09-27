"""Authentication: register (TA only), login, me, password change."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_auth import CurrentUser, get_current_user_optional
from app.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db import crud
from app.db.models import User, UserRole
from app.db.session import get_db
from app.schemas.auth import (
    AuthStatusResponse,
    PasswordChange,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id, email=user.email, full_name=user.full_name, role=user.role, is_active=user.is_active
    )


@router.post("/register", response_model=TokenResponse)
async def register(body: UserCreate, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Self-registration creates **TA** accounts only.

    A new TA has no access to any course until a professor adds them. Professor
    accounts are provisioned by an administrator (``python -m scripts.create_user``),
    so nobody can self-register into grading authority.
    """
    settings = get_settings()
    if not settings.allow_self_registration:
        raise HTTPException(status_code=403, detail="Self-registration is disabled")
    if body.role != UserRole.TA:
        raise HTTPException(
            status_code=403,
            detail="Professor accounts cannot be self-registered; ask an administrator.",
        )
    if await crud.get_user_by_email(db, body.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    user = await crud.create_user(
        db,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=UserRole.TA,
    )
    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=_user_response(user))


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await crud.get_user_by_email(db, body.email)
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    # The role claim is informational only; authorization always reads the DB.
    token = create_access_token(user.id, {"role": user.role.value})
    return TokenResponse(access_token=token, user=_user_response(user))


@router.get("/me", response_model=UserResponse | AuthStatusResponse)
async def me(user: User | None = Depends(get_current_user_optional)) -> UserResponse | AuthStatusResponse:
    if user:
        return _user_response(user)
    if not get_settings().auth_enabled:
        return AuthStatusResponse(auth_enabled=False, message="Authentication is disabled")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


@router.post("/change-password", status_code=204)
async def change_password(
    body: PasswordChange, user: CurrentUser, db: AsyncSession = Depends(get_db)
) -> None:
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    await crud.update_user(db, user, hashed_password=hash_password(body.new_password))


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status() -> AuthStatusResponse:
    settings = get_settings()
    return AuthStatusResponse(
        auth_enabled=settings.auth_enabled,
        allow_self_registration=settings.allow_self_registration,
    )
