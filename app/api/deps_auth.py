"""Authentication dependencies and role guards.

Three layers of checks protect every resource:

1. authentication (``get_current_user``) — a valid, unexpired token for an active user;
2. role (``RequireProfessor`` / ``RequireTA`` / ``RequireProfessorOrTA``);
3. ownership / assignment (``app.api.permissions.require_*_access``).

Roles always come from the database, never from token claims.
"""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import decode_access_token
from app.db import crud
from app.db.models import User, UserRole
from app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """The authenticated user, or None when no valid token was sent."""
    if not credentials:
        return None
    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        return None
    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError:
        return None
    user = await crud.get_user(db, user_id)
    if not user or not user.is_active:
        return None
    return user


async def get_current_user(
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_legacy_actor(
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User | None:
    """Actor for the legacy workbench endpoints (upload / evaluate / results / review).

    With AUTH_ENABLED=true (default) a logged-in user is required and resource
    checks apply. With AUTH_ENABLED=false anonymous callers are allowed, which
    restores the original single-user demo behaviour; a logged-in caller is still
    subject to the normal role and ownership checks.
    """
    if user is not None:
        return user
    if not get_settings().auth_enabled:
        return None
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(*roles: UserRole):
    async def checker(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return checker


def ensure_professor(user: User | None) -> None:
    """Role check for legacy endpoints where ``user`` may be None (open demo mode)."""
    if user is not None and user.role != UserRole.PROFESSOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Professor role required")


RequireProfessor = Depends(require_role(UserRole.PROFESSOR))
RequireTA = Depends(require_role(UserRole.TA))
RequireProfessorOrTA = Depends(require_role(UserRole.PROFESSOR, UserRole.TA))

# Backward-compatible names (INSTRUCTOR was renamed to PROFESSOR).
RequireInstructor = RequireProfessor
RequireTAOrInstructor = RequireProfessorOrTA

CurrentUser = Annotated[User, Depends(get_current_user)]
ProfessorUser = Annotated[User, Depends(require_role(UserRole.PROFESSOR))]
TAUser = Annotated[User, Depends(require_role(UserRole.TA))]
StaffUser = Annotated[User, Depends(require_role(UserRole.PROFESSOR, UserRole.TA))]
LegacyActor = Annotated[User | None, Depends(get_legacy_actor)]
