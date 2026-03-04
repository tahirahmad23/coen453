from __future__ import annotations
import datetime
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import security
from app.core.enums import AuditAction, TargetType
from app.core.exceptions import (
    ForbiddenError,
    NotFoundError,
    TokenAlreadyUsedError,
    TokenExpiredError,
)
from app.modules.audit import service as audit_service
from app.modules.cases.models import Case
from app.modules.tokens.models import PrescriptionToken




async def issue_token(db: AsyncSession, case: Case, base_url: str) -> tuple[PrescriptionToken, str]:
    """
    Precondition: case.outcome == CaseOutcome.PHARMACY
    Called immediately after case creation by engine routes.
    """
    # 1. Check no token already exists for this case
    existing_stmt = select(PrescriptionToken).where(PrescriptionToken.case_id == case.id)
    existing = await db.execute(existing_stmt)
    if existing.scalar_one_or_none() is not None:
        raise ValueError("Token already issued for this case.")

    # 2. Check anomaly: count tokens issued to case.user_id in last 24 hours
    recent_count = await get_token_stats(db, case.user_id, hours=24)
    anomaly = recent_count >= 3

    # 3. Generate token_secret = generate_token_secret()
    token_secret = security.generate_token_secret()
    
    # 4. token_hash = hash_token(token_secret)
    token_hash = security.hash_token(token_secret)
    
    # 5. expires_at = now + 24 hours (UTC)
    now = datetime.datetime.now(datetime.UTC)
    expires_at = now + datetime.timedelta(hours=24)
    
    # 6. Insert PrescriptionToken
    new_token = PrescriptionToken(
        case_id=case.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(new_token)
    await db.flush() # flush to get token.id
    
    # 11. Write audit
    diff = {"anomaly": True, "token_count_24h": recent_count + 1} if anomaly else {}
    await audit_service.log(
        db,
        action=AuditAction.TOKEN_ISSUED,
        target_type=TargetType.TOKEN,
        target_id=new_token.id,
        actor_id=case.user_id,
        diff=diff,
    )
    
    await db.commit()
    await db.refresh(new_token)
    
    # 12. Return (token_record, token_secret)
    return new_token, token_secret


async def get_token_for_student(db: AsyncSession, case_id: uuid.UUID, user_id: uuid.UUID) -> PrescriptionToken:
    """Fetch PrescriptionToken by case_id, verify the case belongs to user_id."""
    stmt = (
        select(PrescriptionToken)
        .options(selectinload(PrescriptionToken.case))
        .where(PrescriptionToken.case_id == case_id)
    )
    result = await db.execute(stmt)
    token = result.scalar_one_or_none()
    
    if not token:
        raise NotFoundError("Token not found.")
        
    if token.case.user_id != user_id:
        raise ForbiddenError("You can only view your own token.")
        
    return token


async def validate_token(db: AsyncSession, token_input: str, pharmacist_id: uuid.UUID) -> PrescriptionToken:
    """
    Validate and consume a token atomically.
    Raises domain exceptions on failure.
    """
    hash_input = security.hash_token(token_input.strip().upper())
    
    from app.modules.cases.models import Case as CaseModel
    # Atomic READ FOR UPDATE
    stmt = (
        select(PrescriptionToken)
        .options(selectinload(PrescriptionToken.case).selectinload(CaseModel.user))
        .where(PrescriptionToken.token_hash == hash_input)
        .with_for_update()
    )
    result = await db.execute(stmt)
    token = result.scalar_one_or_none()
    
    if not token:
        raise NotFoundError("Token not found.")
        
    if token.used_at is not None:
        raise TokenAlreadyUsedError("Token already used.")
        
    now = datetime.datetime.now(datetime.UTC)
    if token.expires_at < now:
        raise TokenExpiredError("Token has expired.")
        
    token.used_at = now
    token.used_by = pharmacist_id
    
    await audit_service.log(
        db,
        action=AuditAction.TOKEN_USED,
        target_type=TargetType.TOKEN,
        target_id=token.id,
        actor_id=pharmacist_id,
        diff={},
    )
    
    await db.commit()
    await db.refresh(token)
    return token


async def get_token_stats(db: AsyncSession, user_id: uuid.UUID, hours: int = 24) -> int:
    """Count how many tokens have been issued to a user's cases in the last N hours."""
    since = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=hours)
    
    stmt = (
        select(func.count(PrescriptionToken.id))
        .join(Case, Case.id == PrescriptionToken.case_id)
        .where(Case.user_id == user_id)
        .where(PrescriptionToken.created_at >= since)
    )
    
    result = await db.execute(stmt)
    return result.scalar_one() or 0