"""Authentication: register, login, me."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_auth import get_current_user, get_current_user_optional
from app.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db import crud
from app.db.models import User, UserRole
from app.db.session import get_db
from app.schemas.auth import TokenResponse, UserCreate, UserLogin, UserResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _user_response(user: User) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name, role=user.role)


@router.post("/register", response_model=TokenResponse)
async def register(body: UserCreate, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    settings = get_settings()
    existing = await crud.get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    count = len(await crud.list_users(db, limit=1))
    role = body.role
    if count == 0:
        role = UserRole.INSTRUCTOR

    if settings.auth_enabled and role == UserRole.INSTRUCTOR and count > 0:
        raise HTTPException(status_code=403, detail="Only first user can self-register as instructor")

    user = await crud.create_user(
        db,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=role,
    )
    token = create_access_token(user.id, {"role": user.role.value})
    return TokenResponse(access_token=token, user=_user_response(user))


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await crud.get_user_by_email(db, body.email)
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    token = create_access_token(user.id, {"role": user.role.value})
    return TokenResponse(access_token=token, user=_user_response(user))


@router.get("/me", response_model=UserResponse | dict)
async def me(user: User | None = Depends(get_current_user_optional)) -> UserResponse | dict:
    settings = get_settings()
    if not settings.auth_enabled:
        return {"auth_enabled": False, "message": "Authentication is disabled"}
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _user_response(user)


@router.get("/status")
async def auth_status() -> dict:
    settings = get_settings()
    return {"auth_enabled": settings.auth_enabled}
