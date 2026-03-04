from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import create_session_cookie
from app.core.templates import templates
from app.modules.auth import service as auth_service
from app.modules.auth.schemas import UserContext
from app.modules.cases import service as case_service
from app.modules.analytics import service as analytics_service
from app.modules.tokens import service as token_service

router = APIRouter(prefix="", tags=["auth"])

@router.get("/", summary="Root redirect")
async def root_redirect(request: Request):
    """Redirect root to dashboard (which redirects to login if unauthenticated)."""
    return RedirectResponse("/dashboard", status_code=303)

@router.get("/login", summary="Show login page")
async def login_page(request: Request):
    """Render the login page with email form."""
    session_cookie = request.cookies.get("ct_session")
    if session_cookie:
        try:
            from app.core.security import decode_session_cookie
            decode_session_cookie(session_cookie)
            return RedirectResponse("/dashboard", status_code=303)
        except Exception:
            # Invalid/Expired session — continue to login page
            pass
    return templates.TemplateResponse(request, "auth/login.html")

@router.get("/register", summary="Show register page")
async def register_page(request: Request):
    """Render the registration page."""
    session_cookie = request.cookies.get("ct_session")
    if session_cookie:
        try:
            from app.core.security import decode_session_cookie
            decode_session_cookie(session_cookie)
            return RedirectResponse("/dashboard", status_code=303)
        except Exception:
            # Invalid/Expired session — continue to register page
            pass
    return templates.TemplateResponse(request, "auth/register.html")

@router.post("/api/v1/auth/login", summary="Login with password")
async def login_route(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),  # noqa: B008
):
    """Authenticate and set session cookie."""
    try:
        user = await auth_service.authenticate_user(db, email, password)
        session_value = create_session_cookie(str(user.id), user.role.value)
        
        response = HTMLResponse(content="", status_code=200)
        response.headers["HX-Redirect"] = "/dashboard"
        from app.core.config import settings
        response.set_cookie(
            key="ct_session",
            value=session_value,
            max_age=604800,
            httponly=True,
            secure=settings.is_production,
            samesite="lax",
        )
        return response
    except Exception as e:
        # Return only the form partial/alert for HTMX or the full page for regular requests
        if request.headers.get("HX-Request"):
            return templates.TemplateResponse(
                request, "auth/login.html", {"error": str(e), "email": email},
                headers={"HX-Retarget": "#auth-card"}
            )
        return templates.TemplateResponse(
            request, "auth/login.html", {"error": str(e), "email": email}
        )


@router.post("/api/v1/auth/register", summary="Register with password")
async def register_route(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),  # noqa: B008
):
    """Register and set session cookie."""
    try:
        user = await auth_service.register_user(db, email, password)
        session_value = create_session_cookie(str(user.id), user.role.value)
        
        response = HTMLResponse(content="", status_code=200)
        response.headers["HX-Redirect"] = "/dashboard"
        from app.core.config import settings
        response.set_cookie(
            key="ct_session",
            value=session_value,
            max_age=604800,
            httponly=True,
            secure=settings.is_production,
            samesite="lax",
        )
        return response
    except Exception as e:
        if request.headers.get("HX-Request"):
            return templates.TemplateResponse(
                request, "auth/register.html", {"error": str(e), "email": email},
                headers={"HX-Retarget": "#auth-card"}
            )
        return templates.TemplateResponse(
            request, "auth/register.html", {"error": str(e), "email": email}
        )

@router.post("/logout", summary="Logout")
async def logout(request: Request):
    """Clear session cookie."""
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("ct_session")
    return response

@router.get("/dashboard", summary="Dashboard placeholder")
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db), # noqa: B008
    current_user: UserContext = Depends(get_current_user),  # noqa: B008
):
    """Protected dashboard."""
    data = {
        "user": current_user,
    }
    
    # Fetch specialized data based on role
    if current_user.role.value == "student":
        history, _ = await case_service.get_student_case_history(db, current_user.id, page=1, page_size=1)
        data["recent_case"] = history[0] if history else None
        
    elif current_user.role.value == "clinician":
        # Clinicians see summary stats and priority cases
        data["summary"] = await analytics_service.get_summary_stats(db)
        # Get cases that need attention (e.g. flagged or recently triaged)
        from app.core.enums import CaseStatus
        priority_cases, _ = await case_service.get_cases_for_clinician(
            db, status=CaseStatus.TRIAGED, page=1, page_size=5
        )
        data["priority_cases"] = priority_cases
        
    elif current_user.role.value == "pharmacist":
        # Pharmacists see recent token validations
        from app.modules.tokens.models import PrescriptionToken
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        stmt = (
            select(PrescriptionToken)
            .options(selectinload(PrescriptionToken.case))
            .where(PrescriptionToken.used_by == current_user.id)
            .order_by(PrescriptionToken.used_at.desc())
            .limit(5)
        )
        result = await db.execute(stmt)
        data["recent_validations"] = list(result.scalars().all())
        
    elif current_user.role.value == "admin":
        # Admins see full system summary
        data["summary"] = await analytics_service.get_summary_stats(db)
        data["recent_activity"] = await analytics_service.get_recent_activity(db, limit=5)

    return templates.TemplateResponse(request, "auth/dashboard.html", data)

@router.get("/components/mobile-menu")
async def mobile_menu(request: Request, current_user = Depends(get_current_user)):
    return templates.TemplateResponse(
        request, "components/mobile_menu.html", {"user": current_user}
    )
