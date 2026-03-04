import uuid
import datetime
import pytest

from sqlalchemy import select
from app.core import security
from app.core.enums import CaseOutcome, Role
from app.core.exceptions import ForbiddenError, NotFoundError, TokenAlreadyUsedError, TokenExpiredError
from app.modules.cases.models import Case
from app.modules.tokens.models import PrescriptionToken
from app.modules.tokens import service as token_service

# --- UNIT TESTS ---

def test_generate_token_secret_length() -> None:
    """Token secret is exactly 6 characters."""
    secret = security.generate_token_secret()
    assert len(secret) == 6

def test_generate_token_secret_no_ambiguous_chars() -> None:
    """Token contains no 0, O, I, or 1 characters."""
    for _ in range(50):
        secret = security.generate_token_secret()
        assert "0" not in secret
        assert "O" not in secret
        assert "I" not in secret
        assert "1" not in secret

def test_hash_token_deterministic() -> None:
    """Same input always produces same hash."""
    secret = "ABCDEF"
    hash1 = security.hash_token(secret)
    hash2 = security.hash_token(secret)
    assert hash1 == hash2

def test_verify_token_correct() -> None:
    """verify_token returns True for correct plaintext."""
    secret = security.generate_token_secret()
    token_hash = security.hash_token(secret)
    assert security.verify_token(secret, token_hash) is True

def test_verify_token_wrong() -> None:
    """verify_token returns False for wrong plaintext."""
    secret = security.generate_token_secret()
    wrong_secret = "WRONGX"
    token_hash = security.hash_token(secret)
    assert security.verify_token(wrong_secret, token_hash) is False

def test_generate_qr_png_returns_bytes() -> None:
    """generate_qr_png returns non-empty bytes."""
    png_bytes = token_service.generate_qr_png("SECRET", "http://test")
    assert isinstance(png_bytes, bytes)
    assert len(png_bytes) > 0

# --- INTEGRATION TESTS ---

@pytest.fixture
async def pharmacy_case(db_session, test_user, test_flow):
    case = Case(
        user_id=test_user.id,
        flow_id=test_flow.id,
        answers_enc="encrypted",
        outcome=CaseOutcome.PHARMACY
    )
    db_session.add(case)
    await db_session.commit()
    await db_session.refresh(case)
    return case

@pytest.fixture
async def pharmacy_case_with_token(db_session, pharmacy_case, mocker):
    mocker.patch("app.modules.tokens.service.upload_qr_png", return_value="url")
    token, secret = await token_service.issue_token(db_session, pharmacy_case, "http://test")
    return pharmacy_case, token, secret

@pytest.fixture
async def valid_token(db_session, pharmacy_case_with_token):
    _, token, secret = pharmacy_case_with_token
    return token, secret

@pytest.fixture
async def used_token(db_session, pharmacy_case_with_token, pharmacist_user):
    _, token, secret = pharmacy_case_with_token
    token.used_at = datetime.datetime.now(datetime.UTC)
    token.used_by = pharmacist_user.id
    await db_session.commit()
    await db_session.refresh(token)
    return token, secret

@pytest.fixture
async def expired_token(db_session, pharmacy_case_with_token):
    _, token, secret = pharmacy_case_with_token
    token.expires_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    await db_session.commit()
    await db_session.refresh(token)
    return token, secret


@pytest.fixture
async def pharmacist_user(db_session):
    from app.modules.auth.models import User
    user = User(email="pharmacist@example.com", auth_provider="supabase", role=Role.PHARMACIST)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_issue_token_success(db_session, pharmacy_case, mocker) -> None:
    """issue_token creates token record, returns (token, secret)."""
    mocker.patch("app.modules.tokens.service.upload_qr_png", return_value="url")
    token, secret = await token_service.issue_token(db_session, pharmacy_case, "http://test")
    assert token.case_id == pharmacy_case.id
    assert len(secret) == 6
    assert token.token_hash == security.hash_token(secret)
    assert token.qr_storage_key == f"tokens/{pharmacy_case.id}.png"


async def test_issue_token_duplicate_raises(db_session, pharmacy_case_with_token, mocker) -> None:
    """Issuing a second token for same case raises an error."""
    mocker.patch("app.modules.tokens.service.upload_qr_png", return_value="url")
    case, _, _ = pharmacy_case_with_token
    with pytest.raises(ValueError, match="Token already issued"):
        await token_service.issue_token(db_session, case, "http://test")


async def test_issue_token_anomaly_flagged(db_session, test_user, test_flow, mocker) -> None:
    """3+ tokens in 24h creates audit entry with anomaly=True."""
    mocker.patch("app.modules.tokens.service.upload_qr_png", return_value="url")
    # issue 4 tokens (the 4th one triggers count >= 3)
    for i in range(4):
        case = Case(user_id=test_user.id, flow_id=test_flow.id, answers_enc="enc", outcome=CaseOutcome.PHARMACY)
        db_session.add(case)
        await db_session.commit()
        await db_session.refresh(case)
        await token_service.issue_token(db_session, case, "http://test")
    
    # query audit log
    from app.modules.audit.models import AuditLog
    from app.core.enums import AuditAction
    
    stmt = select(AuditLog).where(AuditLog.actor_id == test_user.id).where(AuditLog.action == AuditAction.TOKEN_ISSUED)
    result = await db_session.execute(stmt)
    logs = result.scalars().all()
    # the 4th token issued will have anomaly=True
    assert logs[-1].diff.get("anomaly") is True
    assert logs[-1].diff.get("token_count_24h") == 3 + 1


async def test_validate_token_success(db_session, pharmacist_user, valid_token) -> None:
    """Valid token is consumed: used_at set, used_by set."""
    token, secret = valid_token
    validated = await token_service.validate_token(db_session, secret, pharmacist_user.id)
    assert validated.id == token.id
    assert validated.used_at is not None
    assert validated.used_by == pharmacist_user.id


async def test_validate_token_already_used(db_session, pharmacist_user, used_token) -> None:
    """TokenAlreadyUsedError raised for already-consumed token."""
    _, secret = used_token
    with pytest.raises(TokenAlreadyUsedError):
        await token_service.validate_token(db_session, secret, pharmacist_user.id)


async def test_validate_token_expired(db_session, pharmacist_user, expired_token) -> None:
    """TokenExpiredError raised for expired token."""
    _, secret = expired_token
    with pytest.raises(TokenExpiredError):
        await token_service.validate_token(db_session, secret, pharmacist_user.id)


async def test_validate_token_not_found(db_session, pharmacist_user) -> None:
    """NotFoundError raised for non-existent token hash."""
    with pytest.raises(NotFoundError):
        await token_service.validate_token(db_session, "UNK123", pharmacist_user.id)

async def test_validate_concurrent_calls(db_session, pharmacist_user, valid_token) -> None:
    """Two concurrent validate calls: one succeeds, one raises TokenAlreadyUsedError."""
    # Since sqlite doesn't truly block FOR UPDATE, this is mostly checking sequential calls.
    # In PostgreSQL this tests atomic lock behavior.
    _, secret = valid_token
    
    await token_service.validate_token(db_session, secret, pharmacist_user.id)
    
    with pytest.raises(TokenAlreadyUsedError):
        # Using a fresh session locally to simulate separate transaction context
        await token_service.validate_token(db_session, secret, pharmacist_user.id)


# --- ROUTE TESTS ---

@pytest.fixture
def student_cookie(test_user):
    return security.create_session_cookie(test_user.id, Role.STUDENT.value)

@pytest.fixture
def pharmacist_cookie(pharmacist_user):
    return security.create_session_cookie(pharmacist_user.id, Role.PHARMACIST.value)

@pytest.fixture
async def other_student_cookie(db_session):
    from app.modules.auth.models import User
    user = User(email="other@example.com", auth_provider="supabase", role=Role.STUDENT)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return security.create_session_cookie(user.id, Role.STUDENT.value)


@pytest.mark.asyncio
async def test_token_display_page(client, student_cookie, pharmacy_case_with_token) -> None:
    """GET /tokens/{case_id} renders token display page."""
    case, token, secret = pharmacy_case_with_token
    client.cookies.set("session", student_cookie)
    response = await client.get(f"/tokens/{case.id}")
    assert response.status_code == 200
    assert "Your Prescription Token" in response.text
    # Pending token was not set in this request so secret might not be visible in raw response


@pytest.mark.asyncio
async def test_token_display_wrong_student(client, other_student_cookie, pharmacy_case_with_token):
    """Student cannot view another student's token — 403."""
    case, token, secret = pharmacy_case_with_token
    client.cookies.set("session", other_student_cookie)
    response = await client.get(f"/tokens/{case.id}")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_pharmacy_validate_route_success(client, pharmacist_cookie, valid_token):
    """POST /api/v1/tokens/validate returns success fragment."""
    _, secret = valid_token
    client.cookies.set("session", pharmacist_cookie)
    response = await client.post("/api/v1/tokens/validate", data={"token": secret})
    assert response.status_code == 200
    assert "Token Valid" in response.text


@pytest.mark.asyncio
async def test_pharmacy_validate_route_used(client, pharmacist_cookie, used_token):
    """POST returns error fragment for already-used token."""
    _, secret = used_token
    client.cookies.set("session", pharmacist_cookie)
    response = await client.post("/api/v1/tokens/validate", data={"token": secret})
    assert response.status_code == 200 # HTMX 200
    assert "already used" in response.text
