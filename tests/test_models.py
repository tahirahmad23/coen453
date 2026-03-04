from __future__ import annotations
import pytest
from sqlalchemy.exc import IntegrityError
from datetime import datetime, UTC
import uuid

@pytest.mark.asyncio
async def test_create_user(db_session) -> None:
    """User can be created and retrieved."""
    from app.modules.auth.models import User
    
    user = User(email="unique@example.com", auth_provider="supabase")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    assert user.id is not None
    assert user.email == "unique@example.com"
    assert user.created_at is not None
    assert user.updated_at is not None

@pytest.mark.asyncio
async def test_user_email_unique(db_session) -> None:
    """Duplicate email raises IntegrityError."""
    from app.modules.auth.models import User
    
    user1 = User(email="duplicate@example.com", auth_provider="supabase")
    user2 = User(email="duplicate@example.com", auth_provider="supabase")
    
    db_session.add(user1)
    await db_session.commit()
    
    db_session.add(user2)
    with pytest.raises(IntegrityError):
        await db_session.commit()

@pytest.mark.asyncio
async def test_create_symptom_flow(db_session, test_user) -> None:
    """SymptomFlow with JSONB payload can be created."""
    from app.modules.flows.models import SymptomFlow
    from app.core.enums import FlowStatus
    
    flow = SymptomFlow(
        name="Respiratory",
        rule_payload={"start": "q1"},
        created_by=test_user.id,
        status=FlowStatus.ACTIVE
    )
    db_session.add(flow)
    await db_session.commit()
    await db_session.refresh(flow)
    
    assert flow.id is not None
    assert flow.name == "Respiratory"
    assert flow.rule_payload == {"start": "q1"}
    assert flow.created_by == test_user.id

@pytest.mark.asyncio
async def test_create_case(db_session, test_user, test_flow) -> None:
    """Case links to user and flow correctly."""
    from app.modules.cases.models import Case
    from app.core.enums import CaseOutcome
    
    case = Case(
        user_id=test_user.id,
        flow_id=test_flow.id,
        answers_enc="encrypted_data",
        outcome=CaseOutcome.CLINIC
    )
    db_session.add(case)
    await db_session.commit()
    await db_session.refresh(case)
    
    assert case.id is not None
    assert case.user_id == test_user.id
    assert case.flow_id == test_flow.id
    assert case.outcome == CaseOutcome.CLINIC

@pytest.mark.asyncio
async def test_create_prescription_token(db_session, test_case) -> None:
    """Token links to case, token_hash is unique."""
    from app.modules.tokens.models import PrescriptionToken
    
    expires_at = datetime.now(UTC)
    token = PrescriptionToken(
        case_id=test_case.id,
        token_hash="hash_123",
        expires_at=expires_at
    )
    db_session.add(token)
    await db_session.commit()
    await db_session.refresh(token)
    
    assert token.id is not None
    assert token.case_id == test_case.id
    assert token.token_hash == "hash_123"

@pytest.mark.asyncio
async def test_token_case_unique(db_session, test_case) -> None:
    """Second token for same case raises IntegrityError."""
    from app.modules.tokens.models import PrescriptionToken
    
    expires_at = datetime.now(UTC)
    token1 = PrescriptionToken(
        case_id=test_case.id,
        token_hash="hash_abc",
        expires_at=expires_at
    )
    db_session.add(token1)
    await db_session.commit()
    
    token2 = PrescriptionToken(
        case_id=test_case.id,
        token_hash="hash_xyz",
        expires_at=expires_at
    )
    db_session.add(token2)
    with pytest.raises(IntegrityError):
        await db_session.commit()

@pytest.mark.asyncio
async def test_create_audit_log(db_session, test_user) -> None:
    """AuditLog row can be inserted, never updated."""
    from app.modules.audit.models import AuditLog
    from app.core.enums import AuditAction, TargetType
    
    log = AuditLog(
        actor_id=test_user.id,
        action=AuditAction.CASE_CREATED,
        target_type=TargetType.CASE,
        target_id=uuid.uuid4(),
        diff={"score": 10},
        ip_hash="ip_hash_abc"
    )
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)
    
    assert log.id is not None
    assert log.actor_id == test_user.id
    assert log.action == AuditAction.CASE_CREATED
    assert log.target_type == TargetType.CASE

@pytest.mark.asyncio
async def test_audit_log_no_updated_at() -> None:
    """AuditLog model has no updated_at column."""
    from app.modules.audit.models import AuditLog
    
    assert not hasattr(AuditLog, "updated_at")
    assert hasattr(AuditLog, "created_at")
