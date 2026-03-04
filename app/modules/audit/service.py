import datetime
import logging
import uuid
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AuditAction, TargetType
from app.modules.audit.models import AuditLog

logger = logging.getLogger(__name__)


async def log(
    db: AsyncSession,
    action: AuditAction,
    target_type: TargetType,
    target_id: uuid.UUID | None,
    actor_id: uuid.UUID | None = None,
    diff: dict | None = None,
    ip_hash: str | None = None,
) -> None:
    """Append one audit log entry."""
    try:
        entry = AuditLog(
            actor_id=actor_id,
            action=action.value,
            target_type=target_type.value,
            target_id=target_id,
            diff=diff,
            ip_hash=ip_hash,
        )
        db.add(entry)
        await db.flush()
    except Exception:
        logger.exception("Failed to write audit log entry")


async def get_audit_logs(
    db: AsyncSession,
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
    target_type: str | None = None,
    date_from: datetime.datetime | None = None,
    date_to: datetime.datetime | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[AuditLog], int]:
    """Paginated, filterable audit log query."""
    query = select(AuditLog)
    
    if actor_id:
        query = query.where(AuditLog.actor_id == actor_id)
    if action:
        query = query.where(AuditLog.action == action)
    if target_type:
        query = query.where(AuditLog.target_type == target_type)
    if date_from:
        query = query.where(AuditLog.created_at >= date_from)
    if date_to:
        query = query.where(AuditLog.created_at <= date_to)
        
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_count = (await db.execute(count_query)).scalar() or 0
    
    # Apply pagination
    query = query.order_by(desc(AuditLog.created_at)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    logs = list(result.scalars().all())
    
    return logs, total_count


async def get_audit_entry(db: AsyncSession, entry_id: int) -> AuditLog:
    """Fetch single audit entry by ID."""
    result = await db.execute(select(AuditLog).where(AuditLog.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise ValueError(f"Audit entry {entry_id} not found")
    return entry
