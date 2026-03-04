from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.templates import templates
from app.modules.auth.schemas import UserContext
from app.modules.analytics import service as analytics_service
from app.core.exceptions import ForbiddenError

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("", summary="Analytics Dashboard")
async def analytics_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    """View the analytics dashboard."""
    if current_user.role.value not in ["clinician", "admin"]:
        raise ForbiddenError("Only clinicians and admins can access analytics.")

    summary = await analytics_service.get_summary_stats(db)
    outcomes = await analytics_service.get_outcome_distribution(db)
    recent_cases = await analytics_service.get_recent_activity(db)

    return templates.TemplateResponse(
        request,
        "analytics/dashboard.html",
        {
            "user": current_user,
            "summary": summary,
            "outcomes": outcomes,
            "recent_cases": recent_cases,
        },
    )
