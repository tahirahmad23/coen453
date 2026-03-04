from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import Role


class LoginPayload(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)

class RegisterPayload(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str

class UserContext(BaseModel):
    """Injected into request.state after auth — used by all protected routes."""
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    role: Role
    is_active: bool