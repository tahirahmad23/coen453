from __future__ import annotations

import datetime
import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AuditAction, CaseOutcome, CaseStatus, TargetType
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.security import decrypt_field, encrypt_field
from app.modules.audit import service as audit_service
from app.modules.cases.models import Case
from app.modules.cases.schemas import CaseCreateRequest, CaseOverrideRequest


async def create_case(
    db: AsyncSession,
    user_id: uuid.UUID,
    payload: CaseCreateRequest,
) -> Case:
    """Create a new triaged case with encrypted answers and audit log."""
    answers_str = json.dumps(payload.answers)
    case = Case(
        user_id=user_id,
        flow_id=payload.flow_id,
        answers_enc=encrypt_field(answers_str),
        score=payload.score,
        outcome=payload.outcome,
        is_flagged=payload.is_flagged,
        status=CaseStatus.TRIAGED,
        duration_secs=payload.duration_secs,
    )
    db.add(case)
    await db.flush()  # get ID for audit
    
    await audit_service.log(
        db=db,
        action=AuditAction.CASE_CREATED,
        target_type=TargetType.CASE,
        target_id=case.id,
        actor_id=user_id,
    )
    
    await db.commit()
    await db.refresh(case)
    return case


async def get_case_for_student(db: AsyncSession, case_id: uuid.UUID, user_id: uuid.UUID) -> Case:
    """Fetch a case by ID and verify owner."""
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise NotFoundError("Case not found")
    if case.user_id != user_id:
        raise ForbiddenError("You do not have access to this case")
    return case


async def get_cases_for_clinician(
    db: AsyncSession,
    outcome: CaseOutcome | None = None,
    status: CaseStatus | None = None,
    date_from: datetime.datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Case], int]:
    """List cases with filters and pagination for clinicians."""
    stmt = select(Case).order_by(Case.created_at.desc())
    count_stmt = select(func.count()).select_from(Case)
    
    if outcome:
        stmt = stmt.where(Case.outcome == outcome)
        count_stmt = count_stmt.where(Case.outcome == outcome)
    if status:
        stmt = stmt.where(Case.status == status)
        count_stmt = count_stmt.where(Case.status == status)
    if date_from:
        stmt = stmt.where(Case.created_at >= date_from)
        count_stmt = count_stmt.where(Case.created_at >= date_from)
        
    res_count = await db.execute(count_stmt)
    total = res_count.scalar() or 0
    
    stmt = stmt.limit(page_size).offset((page - 1) * page_size)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def get_student_case_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[Case], int]:
    """Fetch paginated case history for a student."""
    stmt = select(Case).where(Case.user_id == user_id).order_by(Case.created_at.desc())
    count_stmt = select(func.count()).select_from(Case).where(Case.user_id == user_id)
    
    res_count = await db.execute(count_stmt)
    total = res_count.scalar() or 0
    
    stmt = stmt.limit(page_size).offset((page - 1) * page_size)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def override_case(
    db: AsyncSession,
    case_id: uuid.UUID,
    clinician_id: uuid.UUID,
    payload: CaseOverrideRequest,
) -> Case:
    """Clinician override of case outcome."""
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise NotFoundError("Case not found")
        
    if case.status == CaseStatus.CLOSED:
        raise ValidationError("Cannot override a closed case")
        
    diff = {
        "before": {"outcome": case.outcome, "status": case.status},
        "after": {"outcome": payload.new_outcome, "status": CaseStatus.OVERRIDDEN}
    }
    
    case.outcome = payload.new_outcome
    case.status = CaseStatus.OVERRIDDEN
    case.override_note = payload.override_note
    case.overridden_by = clinician_id
    
    await audit_service.log(
        db=db,
        action=AuditAction.CASE_OVERRIDDEN,
        target_type=TargetType.CASE,
        target_id=case.id,
        actor_id=clinician_id,
        diff=diff,
    )
    
    await db.commit()
    await db.refresh(case)
    return case


def get_case_answers(case: Case) -> dict:
    """Decrypt and parse answers JSON."""
    plaintext = decrypt_field(case.answers_enc)
    return json.loads(plaintext)


async def get_case_by_id(db: AsyncSession, case_id: uuid.UUID) -> Case | None:
    """Utility used by routes for general access."""
    result = await db.execute(select(Case).where(Case.id == case_id))
    return result.scalar_one_or_none()
