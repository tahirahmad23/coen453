from __future__ import annotations
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.database import Base, get_db
from app.core.config import settings
from httpx import AsyncClient, ASGITransport
from app.main import app
import os

# Import all models to ensure they are registered with Base.metadata before create_all
from app.modules.auth.models import User
from app.modules.cases.models import Case
from app.modules.flows.models import SymptomFlow
from app.modules.tokens.models import PrescriptionToken
from app.modules.audit.models import AuditLog

from sqlalchemy.pool import NullPool

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    # Use a separate test database
    test_db_url = settings.database_url.replace("/campustriage", "/campustriage_test")
    # NullPool ensures no connections are reused across different event loops/tests
    engine = create_async_engine(test_db_url, echo=False, poolclass=NullPool)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture(autouse=True)
async def setup_test_db(test_engine):
    """Ensures a clean database schema before each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield

@pytest_asyncio.fixture
async def db_session(test_engine):
    """Provides a fresh session for each test."""
    SessionLocal = async_sessionmaker(
        bind=test_engine,
        expire_on_commit=False,
    )
    async with SessionLocal() as session:
        yield session
        await session.close()

@pytest_asyncio.fixture(autouse=True)
async def override_get_db(db_session):
    """Overrides the get_db dependency in the FastAPI app for every test."""
    async def _get_db_override():
        yield db_session
    
    app.dependency_overrides[get_db] = _get_db_override
    yield
    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def client():
    """Provides a test client for the FastAPI app."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest_asyncio.fixture
async def test_user(db_session):
    from app.modules.auth.models import User
    from app.core.enums import Role
    user = User(email="test@example.com", auth_provider="supabase", role=Role.STUDENT)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def test_flow(db_session, test_user):
    from app.modules.flows.models import SymptomFlow
    flow = SymptomFlow(name="Test Flow", rule_payload={"nodes": {}}, created_by=test_user.id)
    db_session.add(flow)
    await db_session.commit()
    await db_session.refresh(flow)
    return flow

@pytest_asyncio.fixture
async def test_case(db_session, test_user, test_flow):
    from app.modules.cases.models import Case
    from app.core.enums import CaseStatus
    case = Case(user_id=test_user.id, flow_id=test_flow.id, answers_enc="encrypted", status=CaseStatus.PENDING)
    db_session.add(case)
    await db_session.commit()
    await db_session.refresh(case)
    return case
@pytest_asyncio.fixture
async def admin_user(db_session):
    from app.modules.auth.models import User
    from app.core.enums import Role
    user = User(email="admin@example.com", auth_provider="supabase", role=Role.ADMIN)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def clinician_user(db_session):
    from app.modules.auth.models import User
    from app.core.enums import Role
    user = User(email="clinician@example.com", auth_provider="supabase", role=Role.CLINICIAN)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def student_user(db_session):
    from app.modules.auth.models import User
    from app.core.enums import Role
    user = User(email="student@example.com", auth_provider="supabase", role=Role.STUDENT, student_id="STU001")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user
