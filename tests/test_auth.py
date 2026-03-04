from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.main import app
from app.modules.auth.models import User

# Using global client fixture from conftest.py

@pytest.mark.asyncio
async def test_register_user(client: AsyncClient, db_session: AsyncSession):
    response = await client.post(
        "/api/v1/auth/register",
        data={"email": "newuser@example.com", "password": "securepassword123"}
    )
    assert response.status_code == 200
    assert "session=" in response.headers.get("set-cookie", "")
    assert response.headers.get("hx-redirect") == "/dashboard"
    
    result = await db_session.execute(select(User).where(User.email == "newuser@example.com"))
    user_record = result.scalars().first()
    assert user_record is not None
    assert user_record.password_hash is not None


@pytest.mark.asyncio
async def test_register_duplicate_user(client: AsyncClient, db_session: AsyncSession):
    # First registration
    await client.post(
        "/api/v1/auth/register",
        data={"email": "dup@example.com", "password": "securepassword123"}
    )

    # Second registration
    response = await client.post(
        "/api/v1/auth/register",
        data={"email": "dup@example.com", "password": "securepassword123"}
    )
    
    assert response.status_code == 200
    assert "User with this email already exists." in response.text
    

@pytest.mark.asyncio
async def test_login_user(client: AsyncClient, db_session: AsyncSession):
    # Register first
    await client.post(
        "/api/v1/auth/register",
        data={"email": "login@example.com", "password": "correctpassword"}
    )

    # Login
    response = await client.post(
        "/api/v1/auth/login",
        data={"email": "login@example.com", "password": "correctpassword"}
    )
    
    assert response.status_code == 200
    assert "session=" in response.headers.get("set-cookie", "")
    assert response.headers.get("hx-redirect") == "/dashboard"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, db_session: AsyncSession):
    # Register first
    await client.post(
        "/api/v1/auth/register",
        data={"email": "wrongpass@example.com", "password": "correctpassword"}
    )

    # Login with wrong password
    response = await client.post(
        "/api/v1/auth/login",
        data={"email": "wrongpass@example.com", "password": "wrongpassword"}
    )
    
    assert response.status_code == 200
    assert "Incorrect email or password." in response.text


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient, db_session: AsyncSession):
    response = await client.post(
        "/api/v1/auth/login",
        data={"email": "nonexistent@example.com", "password": "somepassword"}
    )
    
    assert response.status_code == 200
    assert "Incorrect email or password." in response.text
