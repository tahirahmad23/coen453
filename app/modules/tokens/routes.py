from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.enums import Role
from app.core.exceptions import (
    NotFoundError,
    TokenAlreadyUsedError,
    TokenExpiredError,
)
from app.core.templates import templates
from app.modules.auth.schemas import UserContext
from app.modules.tokens import service as token_service

router = APIRouter(prefix="", tags=["tokens"])

@router.get("/tokens/{case_id}", summary="Student token display")
async def token_display(
    case_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.STUDENT)),
):
    """View a token for a given case."""
    token = await token_service.get_token_for_student(db, case_id, current_user.id)
    now = datetime.datetime.now(datetime.UTC)
    
    is_used = token.used_at is not None
    is_expired = token.expires_at <= now

    # Calculate time remaining
    time_remaining = "Expired"
    if token.expires_at > now:
        diff = token.expires_at - now
        hours, remainder = divmod(diff.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        time_remaining = f"{hours}h {minutes}m"

    # Pending token stored in the itsdangerous cookie by engine/routes.py
    from app.core.security import decode_session_cookie
    from itsdangerous import URLSafeTimedSerializer
    from app.core.config import settings as _settings

    token_secret = None
    raw_cookie = request.cookies.get("session")
    if raw_cookie:
        try:
            data = decode_session_cookie(raw_cookie)
            pending = data.pop("pending_token", None)
            if pending and pending.get("case_id") == str(case_id):
                token_secret = pending.get("secret")
                # Clear it from cookie so it's shown only once
                s = URLSafeTimedSerializer(_settings.secret_key)
                from starlette.responses import Response
                # We'll set cleared cookie on the template response below
        except Exception:
            pass

    context = {
        "request": request,
        "token": token,
        "case_id": case_id,
        "time_remaining": time_remaining,
        "token_secret": token_secret,
        "is_used": is_used,
        "is_expired": is_expired,
    }
    response = templates.TemplateResponse(request, "tokens/token_display.html", context)

    # If we just consumed the token secret, clear it from the cookie
    if token_secret and raw_cookie:
        try:
            data = decode_session_cookie(raw_cookie)
            data.pop("pending_token", None)
            s = URLSafeTimedSerializer(_settings.secret_key)
            new_cookie = s.dumps(data)
            response.set_cookie(
                key="session",
                value=new_cookie,
                max_age=604800,
                httponly=True,
                secure=_settings.is_production,
                samesite="lax",
            )
        except Exception:
            pass

    return response





@router.get("/pharmacy/validate", summary="Pharmacy validate screen")
async def pharmacy_validate_page(
    request: Request,
    current_user: UserContext = Depends(require_role(Role.PHARMACIST)),
):
    """Scanner input page for pharmacists."""
    return templates.TemplateResponse(request, "tokens/pharmacy_scanner.html", {"request": request})


@router.post("/api/v1/tokens/validate", summary="Validate token")
async def validate_token_endpoint(
    request: Request,
    token: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.PHARMACIST)),
):
    """Validate token via HTMX form submission."""
    try:
        validated_token = await token_service.validate_token(db, token, current_user.id)

        # Resolve prescriptions from the associated flow's outcome node
        prescriptions = []
        case = validated_token.case
        if case and case.flow_id:
            from sqlalchemy import select
            from app.modules.flows.models import SymptomFlow
            from app.modules.engine.schemas import RulePayload, OutcomeNode

            flow_result = await db.execute(
                select(SymptomFlow).where(SymptomFlow.id == case.flow_id)
            )
            flow = flow_result.scalar_one_or_none()
            if flow and case.outcome:
                try:
                    rule = RulePayload.model_validate(flow.rule_payload)
                    for node in rule.nodes.values():
                        if isinstance(node, OutcomeNode) and node.result == case.outcome:
                            prescriptions = node.prescriptions
                            break
                except Exception:
                    pass

        return templates.TemplateResponse(
            request,
            "tokens/partials/validate_success.html",
            {"request": request, "token": validated_token, "prescriptions": prescriptions}
        )
    except TokenAlreadyUsedError as e:
        return templates.TemplateResponse(
            request,
            "tokens/partials/validate_error.html",
            {"request": request, "error_message": str(e)}
        )
    except TokenExpiredError as e:
        return templates.TemplateResponse(
            request,
            "tokens/partials/validate_error.html",
            {"request": request, "error_message": str(e)}
        )
    except NotFoundError as e:
        return templates.TemplateResponse(
            request,
            "tokens/partials/validate_error.html",
            {"request": request, "error_message": str(e)}
        )