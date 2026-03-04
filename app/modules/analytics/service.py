from __future__ import annotations

import datetime
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cases.models import Case
from app.modules.tokens.models import PrescriptionToken
from app.core.enums import CaseOutcome, CaseStatus

async def get_summary_stats(db: AsyncSession) -> dict:
    """Get high-level summary statistics."""
    total_cases_stmt = select(func.count(Case.id))
    flagged_cases_stmt = select(func.count(Case.id)).where(Case.is_flagged == True)
    tokens_issued_stmt = select(func.count(PrescriptionToken.id))
    tokens_used_stmt = select(func.count(PrescriptionToken.id)).where(PrescriptionToken.used_at.is_not(None))

    total_cases = await db.scalar(total_cases_stmt) or 0
    flagged_cases = await db.scalar(flagged_cases_stmt) or 0
    tokens_issued = await db.scalar(tokens_issued_stmt) or 0
    tokens_used = await db.scalar(tokens_used_stmt) or 0

    return {
        "total_cases": total_cases,
        "flagged_cases": flagged_cases,
        "tokens_issued": tokens_issued,
        "tokens_used": tokens_used,
    }

async def get_outcome_distribution(db: AsyncSession) -> dict:
    """Get the distribution of case outcomes."""
    stmt = select(Case.outcome, func.count(Case.id)).group_by(Case.outcome)
    result = await db.execute(stmt)
    
    # Extract results and handle enum names
    dist = {getattr(outcome, 'name', 'UNKNOWN'): count for outcome, count in result.all() if outcome}
    
    # Ensure all outcomes are present
    for outcome in CaseOutcome:
        if outcome.name not in dist:
            dist[outcome.name] = 0
            
    return dist

async def get_recent_activity(db: AsyncSession, limit: int = 5) -> list[Case]:
    """Get recent cases for the activity feed."""
    stmt = select(Case).order_by(Case.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()
