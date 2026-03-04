import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.enums import Role
from app.core.templates import templates
from app.modules.auth.schemas import UserContext
from app.modules.audit import service as audit_service

router = APIRouter(prefix="", tags=["audit"])


@router.get("/admin/audit", summary="View audit log page")
async def view_audit_log(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.ADMIN)),
):
    """Render the main audit log page."""
    logs, total = await audit_service.get_audit_logs(db, page=1, page_size=50)
    return templates.TemplateResponse(request, "audit/audit_log.html", {
        "logs": logs,
        "total": total,
        "user": current_user,
        "current_page": 1,
        "page_size": 50,
    })


@router.get("/api/v1/admin/audit", summary="Get filtered audit data")
async def get_filtered_audit(
    request: Request,
    action: str | None = Query(None),
    target_type: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.ADMIN)),
):
    """Return filtered audit log table fragment (HTMX)."""
    df = None
    dt = None
    if date_from:
        try:
            df = datetime.fromisoformat(date_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to)
        except ValueError:
            pass
            
    logs, total = await audit_service.get_audit_logs(
        db,
        action=action if action != "all" else None,
        target_type=target_type if target_type != "all" else None,
        date_from=df,
        date_to=dt,
        page=page,
        page_size=50
    )
    
    return templates.TemplateResponse(request, "audit/partials/audit_table.html", {
        "logs": logs,
        "total": total,
        "current_page": page,
        "page_size": 50,
    })


@router.get("/api/v1/admin/audit/{entry_id}/diff", summary="Get audit entry diff modal")
async def get_audit_diff_modal(
    request: Request,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.ADMIN)),
):
    """Return the diff modal fragment for a specific audit entry."""
    entry = await audit_service.get_audit_entry(db, entry_id)
    return templates.TemplateResponse(request, "audit/partials/diff_modal.html", {
        "entry": entry
    })
