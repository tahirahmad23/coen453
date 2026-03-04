from __future__ import annotations

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.exceptions import AuthError, ForbiddenError
from app.core.templates import templates

# import all routers here
from app.modules.auth.routes import router as auth_router
from app.modules.cases.routes import router as cases_router
from app.modules.engine.routes import router as engine_router
from app.modules.flows.routes import router as flows_router
from app.modules.tokens.routes import router as tokens_router
from app.modules.analytics.routes import router as analytics_router
from app.modules.audit.routes import router as audit_router
from app.modules.integrations.routes import router as integrations_router

if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)

from starlette.middleware.sessions import SessionMiddleware

app = FastAPI(title="CampusTriage", docs_url="/docs" if not settings.is_production else None)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, session_cookie="ct_flash")
 
@app.middleware("http")
async def add_user_to_state(request: Request, call_next):
    """Ensure request.state.user is available for templates even if get_current_user isn't called."""
    if not hasattr(request.state, "user"):
        session_cookie = request.cookies.get("ct_session")
        request.state.user = None
        if session_cookie:
            try:
                from app.core.security import decode_session_cookie
                from app.core.enums import Role
                data = decode_session_cookie(session_cookie)
                
                # Mock a minimal user object for templates
                class SimpleUser:
                    def __init__(self, uid, role_val):
                        self.id = uid
                        self.role = Role(role_val)
                
                request.state.user = SimpleUser(data["user_id"], data["role"])
            except Exception:
                pass
    return await call_next(request)
 
# Include all routers
app.include_router(auth_router)
app.include_router(engine_router)
app.include_router(flows_router)
app.include_router(cases_router)
app.include_router(tokens_router)
app.include_router(analytics_router)
app.include_router(audit_router)
app.include_router(integrations_router)
 
@app.exception_handler(AuthError)
async def auth_error_handler(request: Request, exc: AuthError):
    if request.headers.get("HX-Request"):
        # HTMX request — return error HTML fragment
        return templates.TemplateResponse(
            request,
            "components/alert_fragment.html",
            {"message": str(exc), "type": "error"},
            status_code=401,
            headers={"HX-Reswap": "none"},
        )
    # Regular browser request — redirect to login
    request.session["flash"] = {"type": "error", "message": str(exc)}
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("ct_session")
    return response

@app.exception_handler(ForbiddenError)
async def forbidden_handler(request: Request, exc: ForbiddenError):
    return templates.TemplateResponse(
        request, "errors/403.html", status_code=403
    )

@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint for uptime monitoring."""
    return {"status": "ok", "environment": settings.environment}

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception):
    return templates.TemplateResponse(request, "errors/404.html", status_code=404)

@app.exception_handler(500)
async def server_error_handler(request: Request, exc: Exception):
    return templates.TemplateResponse(request, "errors/500.html", status_code=500)
