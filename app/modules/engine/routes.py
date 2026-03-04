from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.enums import CaseOutcome, Role
from app.core.security import decode_session_cookie
from app.core.templates import templates
from app.modules.auth.schemas import UserContext
from app.modules.cases import service as case_service
from app.modules.engine import service as engine_service
from app.modules.engine.schemas import OutcomeNode, QuestionNode, RulePayload
from app.modules.flows import service as flow_service
from app.modules.tokens import service as token_service

router = APIRouter(prefix="", tags=["triage"])

@router.get("/triage", summary="Start or resume triage")
async def triage_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.STUDENT)),
):
    """Start or resume a triage session."""
    active_flow = await flow_service.get_active_flow(db)
    if not active_flow:
        return templates.TemplateResponse(request, "engine/flow_unavailable.html")
    
    # Load state from session
    session_data = request.cookies.get("session")
    data = decode_session_cookie(session_data) if session_data else {}
    triage = data.get("triage")
    
    flow_id = str(active_flow.id)
    rule = RulePayload.model_validate(active_flow.rule_payload)
    
    is_new_session = False
    if triage and triage.get("flow_id") == flow_id:
        current_node_id = triage["current_node_id"]
    else:
        is_new_session = True
        # Initialize fresh state
        current_node_id = rule.start_node
        triage = {
            "flow_id": flow_id,
            "current_node_id": current_node_id,
            "answers": {},
            "score": 0,
            "started_at": datetime.datetime.now(datetime.UTC).isoformat(),
        }
        data["triage"] = triage
    
    node = engine_service.get_node(rule, current_node_id)
    
    # Calculate progress
    total_estimated = len([n for n in rule.nodes.values() if isinstance(n, QuestionNode)])
    current_count = len(triage["answers"]) + 1
    progress = {
        "current": current_count,
        "total": total_estimated,
        "percent": int((current_count - 1) / total_estimated * 100) if total_estimated else 0
    }
    
    context = {
        "node": node,
        "node_id": current_node_id,
        "progress": progress,
        "can_go_back": len(triage["answers"]) > 0,
        "selected_option": triage["answers"].get(current_node_id)
    }
    
    response = templates.TemplateResponse(request, "triage/triage.html", context)
    
    # Update cookie if it was a fresh start
    if is_new_session:
        from itsdangerous import URLSafeTimedSerializer

        from app.core.config import settings
        s = URLSafeTimedSerializer(settings.secret_key)
        new_cookie = s.dumps(data)
        response.set_cookie(
            key="session",
            value=new_cookie,
            max_age=604800,
            httponly=True,
            secure=settings.is_production,
            samesite="lax",
        )
        
    return response

@router.post("/api/v1/engine/answer", summary="Submit answer")
async def submit_answer(
    request: Request,
    node_id: str = Form(...),
    option_label: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.STUDENT)),
):
    """Handle answer submission via HTMX."""
    active_flow = await flow_service.get_active_flow(db)
    if not active_flow:
        return HTMLResponse("Flow unavailable (no active flow found in DB)", status_code=400)
    
    session_data = request.cookies.get("session")
    if not session_data:
        return HTMLResponse("Missing session cookie", status_code=400)
        
    data = decode_session_cookie(session_data)
    triage = data.get("triage")
    
    if not triage:
        return HTMLResponse("No triage session found in cookie", status_code=400)
        
    if triage["current_node_id"] != node_id:
        return HTMLResponse(f"Triage state mismatch: expected {triage['current_node_id']} but got {node_id}", status_code=400)
    
    rule = RulePayload.model_validate(active_flow.rule_payload)
    
    # 1. Advance
    next_node_id, score_delta = engine_service.advance(rule, node_id, option_label)
    
    # 2. Update state
    triage["answers"][node_id] = option_label
    triage["score"] += score_delta
    triage["current_node_id"] = next_node_id
    
    # Check red flag
    is_emergency = node_id in rule.red_flags
    
    next_node = engine_service.get_node(rule, next_node_id)
    
    # 3. Handle outcome or next question
    if is_emergency or isinstance(next_node, OutcomeNode):
        # Determine final outcome
        if is_emergency:
            result_outcome = CaseOutcome.EMERGENCY
            # Override next_node to an emergency outcome node if needed?
            # Or just use the one reached if it is emergency.
            # Usually red flag force-exits.
        else:
            result_outcome = next_node.result
            
        # Create Case
        duration = None
        if "started_at" in triage:
            started = datetime.datetime.fromisoformat(triage["started_at"])
            duration = int((datetime.datetime.now(datetime.UTC) - started).total_seconds())
            
        from app.modules.cases.schemas import CaseCreateRequest
        payload = CaseCreateRequest(
            flow_id=active_flow.id,
            answers=triage["answers"],
            score=triage["score"],
            outcome=result_outcome,
            is_flagged=is_emergency,
            duration_secs=duration,
        )
        case = await case_service.create_case(
            db=db,
            user_id=current_user.id,
            payload=payload,
        )
        
        # Check if we should issue a token
        if result_outcome == CaseOutcome.PHARMACY and isinstance(next_node, OutcomeNode) and next_node.issue_token:
            base_url = str(request.base_url).rstrip("/")
            _, token_secret = await token_service.issue_token(db, case, base_url)
            # Add to pending tokens in the cookie data
            data["pending_token"] = {
                "case_id": str(case.id),
                "secret": token_secret,
            }

        # Clear triage
        if "triage" in data:
            del data["triage"]

        from itsdangerous import URLSafeTimedSerializer

        from app.core.config import settings
        s = URLSafeTimedSerializer(settings.secret_key)
        new_cookie = s.dumps(data)
        
        response = HTMLResponse(content="", status_code=200)
        response.headers["HX-Redirect"] = f"/cases/{case.id}"
        response.set_cookie(
            key="session",
            value=new_cookie,
            max_age=604800,
            httponly=True,
            secure=settings.is_production,
            samesite="lax",
        )
        return response

    # Next question
    total_estimated = len([n for n in rule.nodes.values() if isinstance(n, QuestionNode)])
    current_count = len(triage["answers"]) + 1
    progress = {
        "current": current_count,
        "total": total_estimated,
        "percent": int((current_count - 1) / total_estimated * 100) if total_estimated else 0
    }
    
    context = {
        "request": request,
        "node": next_node,
        "node_id": next_node_id,
        "progress": progress,
        "can_go_back": True,
        "selected_option": None
    }
    
    response = templates.TemplateResponse(request, "engine/question_card.html", context)
    
    # Update cookie
    from itsdangerous import URLSafeTimedSerializer

    from app.core.config import settings
    s = URLSafeTimedSerializer(settings.secret_key)
    new_cookie = s.dumps(data)
    response.set_cookie(
        key="session",
        value=new_cookie,
        max_age=604800,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )
    return response

@router.get("/api/v1/engine/previous", summary="Go back")
async def go_back(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.STUDENT)),
):
    """Handle 'Back' button via HTMX."""
    active_flow = await flow_service.get_active_flow(db)
    if not active_flow:
        return HTMLResponse("Flow unavailable", status_code=400)
        
    session_data = request.cookies.get("session")
    data = decode_session_cookie(session_data)
    triage = data.get("triage")
    
    if not triage or not triage["answers"]:
        return HTMLResponse("Cannot go back", status_code=400)
    
    rule = RulePayload.model_validate(active_flow.rule_payload)
    
    # Pop last answer
    last_node_id = list(triage["answers"].keys())[-1]
    last_label = triage["answers"].pop(last_node_id)
    
    # Re-calculate score (simpler than storing individual deltas)
    # or just subtract? advance returns score_delta.
    _, score_delta = engine_service.advance(rule, last_node_id, last_label)
    triage["score"] -= score_delta
    triage["current_node_id"] = last_node_id
    
    node = engine_service.get_node(rule, last_node_id)
    
    total_estimated = len([n for n in rule.nodes.values() if isinstance(n, QuestionNode)])
    current_count = len(triage["answers"]) + 1
    progress = {
        "current": current_count,
        "total": total_estimated,
        "percent": int((current_count - 1) / total_estimated * 100) if total_estimated else 0
    }
    
    context = {
        "request": request,
        "node": node,
        "node_id": last_node_id,
        "progress": progress,
        "can_go_back": len(triage["answers"]) > 0,
        "selected_option": last_label
    }
    
    response = templates.TemplateResponse(request, "engine/question_card.html", context)
    
    from itsdangerous import URLSafeTimedSerializer

    from app.core.config import settings
    s = URLSafeTimedSerializer(settings.secret_key)
    new_cookie = s.dumps(data)
    response.set_cookie(
        key="session",
        value=new_cookie,
        max_age=604800,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )
    return response

@router.post("/api/v1/engine/restart", summary="Restart triage")
async def restart_triage(
    request: Request,
    current_user: UserContext = Depends(require_role(Role.STUDENT)),
):
    """Clear triage session and restart."""
    session_data = request.cookies.get("session")
    data = decode_session_cookie(session_data)
    if "triage" in data:
        del data["triage"]
        
    response = RedirectResponse(url="/triage", status_code=303)
    
    from itsdangerous import URLSafeTimedSerializer

    from app.core.config import settings
    s = URLSafeTimedSerializer(settings.secret_key)
    new_cookie = s.dumps(data)
    response.set_cookie(
        key="session",
        value=new_cookie,
        max_age=604800,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )
    return response
