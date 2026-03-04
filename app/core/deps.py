from __future__ import annotations

import uuid

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Role
from app.core.exceptions import AuthError, ForbiddenError
from app.core.security import decode_session_cookie
from app.modules.auth.models import User
from app.modules.auth.schemas import UserContext


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> UserContext:
    """Read session cookie and return authenticated user context."""
    session_cookie = request.cookies.get("ct_session")
    if not session_cookie:
        raise AuthError("Not authenticated.")
    
    session_data = decode_session_cookie(session_cookie)
    user = await db.get(User, uuid.UUID(session_data["user_id"]))
    
    if not user or not user.is_active:
        raise AuthError("User not found or inactive.")
    
    current_user = UserContext.model_validate(user)
    request.state.user = current_user
    return current_user

def require_role(*roles: Role):
    """FastAPI dependency factory for role-based access control."""
    async def _check(current_user: UserContext = Depends(get_current_user)) -> UserContext:  # noqa: B008
        if current_user.role not in roles:
            raise ForbiddenError(f"Role '{current_user.role}' is not permitted here.")
        return current_user
    return _check
