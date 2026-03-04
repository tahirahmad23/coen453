from __future__ import annotations

import datetime

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import Role
from app.core.exceptions import AuthError
from app.modules.auth.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    """Authenticate a user with email and password."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if not user:
        raise AuthError("Incorrect email or password.")
        
    if not user.password_hash or not pwd_context.verify(password, user.password_hash):
        raise AuthError("Incorrect email or password.")
        
    if not user.is_active:
        raise AuthError("Inactive user.")
        
    return user


async def register_user(db: AsyncSession, email: str, password: str) -> User:
    """Register a new user with email and password."""
    # Check if user already exists
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise AuthError("User with this email already exists.")
        
    password_hash = pwd_context.hash(password)
    user = User(email=email, password_hash=password_hash, role=Role.STUDENT, is_active=True)
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return user

def create_access_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=15),
        "iat": datetime.datetime.now(datetime.UTC),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")

def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except JWTError as e:
        raise AuthError("Invalid or expired token.") from e
