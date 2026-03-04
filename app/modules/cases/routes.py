from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.enums import CaseOutcome, CaseStatus, Role
from app.core.templates import templates
from app.modules.auth.schemas import UserContext
from app.modules.cases import service as case_service
from app.modules.cases.schemas import CaseOverrideRequest

router = APIRouter(prefix="", tags=["cases"])


@router.get("/cases/history", summary="My assessment history")
async def student_history(
    request: Request,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.STUDENT)),
):
    """View personal triage history."""
    cases, total = await case_service.get_student_case_history(db, current_user.id, page=page)
    return templates.TemplateResponse(
        request,
        "cases/history.html",
        {"cases": cases, "total": total, "page": page, "page_size": 10},
    )


@router.get("/cases/{case_id}", summary="Triage result")
async def case_result_page(
    request: Request,
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.STUDENT, Role.CLINICIAN, Role.ADMIN)),
):
    """View specific triage result."""
    if current_user.role == Role.STUDENT:
        case = await case_service.get_case_for_student(db, case_id, current_user.id)
    else:
        case = await case_service.get_case_by_id(db, case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

    # Task 06 will add token loading here
    token = None

    # Load prescription recommendations from the flow's outcome node
    prescriptions = []
    outcome_message = None
    if case.flow_id and case.outcome:
        from sqlalchemy import select as sa_select
        from app.modules.flows.models import SymptomFlow
        from app.modules.engine.schemas import RulePayload, OutcomeNode

        flow_result = await db.execute(sa_select(SymptomFlow).where(SymptomFlow.id == case.flow_id))
        flow = flow_result.scalar_one_or_none()
        if flow:
            try:
                rule = RulePayload.model_validate(flow.rule_payload)
                for node in rule.nodes.values():
                    if isinstance(node, OutcomeNode) and node.result == case.outcome:
                        prescriptions = node.prescriptions
                        outcome_message = node.message
                        break
            except Exception:
                pass

    return templates.TemplateResponse(request, "cases/result.html", {
        "case": case,
        "token": token,
        "prescriptions": prescriptions,
        "outcome_message": outcome_message,
    })


@router.get("/clinician/cases", summary="Manage cases")
async def clinician_case_list(
    request: Request,
    outcome: CaseOutcome | None = None,
    status: CaseStatus | None = None,
    date_from: datetime.date | None = None,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.CLINICIAN, Role.ADMIN)),
):
    """Filter and view all cases."""
    dt_from = datetime.datetime.combine(date_from, datetime.time.min) if date_from else None
    cases, total = await case_service.get_cases_for_clinician(
        db, outcome=outcome, status=status, date_from=dt_from, page=page
    )

    context = {
        "request": request,
        "cases": cases,
        "total": total,
        "page": page,
        "page_size": 20,
        "filters": {"outcome": outcome, "status": status, "date_from": date_from},
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "clinician/partials/case_table.html", context)

    return templates.TemplateResponse(request, "clinician/case_list.html", context)


@router.get("/clinician/cases/{case_id}", summary="Review case detail")
async def clinician_case_detail(
    request: Request,
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.CLINICIAN, Role.ADMIN)),
):
    """View case details including decrypted answers."""
    case = await case_service.get_case_by_id(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    answers = case_service.get_case_answers(case)

    return templates.TemplateResponse(
        request, "clinician/case_detail.html", {"case": case, "answers": answers}
    )


@router.put("/api/v1/cases/{case_id}/override", summary="Override outcome")
async def override_case_route(
    request: Request,
    case_id: uuid.UUID,
    new_outcome: CaseOutcome = Form(...),
    override_note: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.CLINICIAN, Role.ADMIN)),
):
    """Apply clinician override."""
    payload = CaseOverrideRequest(new_outcome=new_outcome, override_note=override_note)
    case = await case_service.override_case(db, case_id, current_user.id, payload)

    return templates.TemplateResponse(
        request, "cases/partials/override_success.html", {"case": case}
    )
