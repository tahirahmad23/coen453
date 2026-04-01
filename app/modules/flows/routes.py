import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.enums import Role
from app.core.templates import templates
from app.modules.auth.schemas import UserContext
from app.modules.flows import service as flow_service

router = APIRouter(prefix="", tags=["flows"])


@router.get("/admin/flows", summary="List all flows")
async def list_flows_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.CLINICIAN, Role.ADMIN)),
):
    """Render the flows management page."""
    flows = await flow_service.list_flows(db)
    return templates.TemplateResponse(request, "flows/flow_list.html", {
        "flows": flows,
        "user": current_user,
    })


@router.get("/admin/flows/new-modal", summary="Get upload modal fragment")
async def get_upload_modal(
    request: Request,
    current_user: UserContext = Depends(require_role(Role.ADMIN)),
):
    """Return the upload flow modal fragment."""
    return templates.TemplateResponse(request, "flows/upload_modal.html", {})


@router.get("/admin/flows/{flow_id}/edit-modal", summary="Get edit modal fragment")
async def get_edit_modal(
    request: Request,
    flow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.ADMIN)),
):
    """Return the edit flow modal fragment."""
    flow = await flow_service.get_flow_by_id(db, flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return templates.TemplateResponse(request, "flows/edit_modal.html", {"flow": flow})


@router.get("/admin/flows/{flow_id}", summary="View flow detail")
async def view_flow_detail(
    request: Request,
    flow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.CLINICIAN, Role.ADMIN)),
):
    """Render a specific flow detail page."""
    flow = await flow_service.get_flow_by_id(db, flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    return templates.TemplateResponse(request, "flows/flow_detail.html", {
        "flow": flow,
        "user": current_user,
    })


@router.post("/api/v1/admin/flows", summary="Create new draft flow")
async def create_flow_route(
    request: Request,
    name: str = Form(...),
    rule_payload_json: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.ADMIN)),
):
    """Create a new flow draft with HTMX OOB swap."""
    try:
        flow = await flow_service.create_flow(db, name, rule_payload_json, current_user.id)
        
        # OOB Swap: Clear modal and prepend new card to list
        response_html = templates.get_template("flows/partials/flow_card.html").render({
            "flow": flow,
            "user": current_user,
            "hx_swap_oob": "afterbegin",
            "hx_target": "#flow-list"
        })
        
        # Clear modal container
        response_html += '<div id="modal-container" hx-swap-oob="innerHTML"></div>'
        
        return HTMLResponse(content=response_html)
    except ValueError as e:
        # Return 200 for HTMX so the error fragment is swapped into the modal
        return templates.TemplateResponse(request, "flows/partials/upload_error.html", {
            "error": str(e)
        }, status_code=200)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error creating flow")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")
@router.put("/api/v1/admin/flows/{flow_id}", summary="Update flow")
async def update_flow_route(
    request: Request,
    flow_id: uuid.UUID,
    name: str = Form(...),
    rule_payload_json: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.ADMIN)),
):
    """Update an existing flow draft."""
    try:
        flow = await flow_service.update_flow(db, flow_id, name, rule_payload_json, current_user.id)
        
        # If HTMX, return a redirect header so the browser refreshes the whole page
        if request.headers.get("HX-Request"):
            response = Response(status_code=204)
            response.headers["HX-Redirect"] = f"/admin/flows/{flow_id}"
            return response
            
        return RedirectResponse(url=f"/admin/flows/{flow_id}", status_code=303)
    except ValueError as e:
        # Return 200 for HTMX so the error message is swapped into the container
        return HTMLResponse(content=f'<div class="text-red-400 text-xs p-2">{str(e)}</div>', status_code=200)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error updating flow")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")


@router.delete("/api/v1/admin/flows/{flow_id}", summary="Delete flow")
async def delete_flow_route(
    request: Request,
    flow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.ADMIN)),
):
    """Delete a flow."""
    try:
        success = await flow_service.delete_flow(db, flow_id, current_user.id)
        if not success:
            raise HTTPException(status_code=404, detail="Flow not found")
        
        # If HTMX, return empty response or OOB to remove card
        if request.headers.get("HX-Request"):
            return HTMLResponse(content="", headers={"HX-Trigger": "flowDeleted"})
            
        return RedirectResponse(url="/admin/flows", status_code=303)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error deleting flow")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")

@router.put("/api/v1/admin/flows/{flow_id}/submit", summary="Submit for approval")
async def submit_flow_route(
    request: Request,
    flow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.ADMIN)),
):
    """Submit a flow for approval."""
    try:
        # Admins can submit any flow, so we don't strictly enforce creator here
        # or we explicitly allow it for admins in the service if needed.
        # Currently the service checks it: if flow.created_by != submitted_by_id: raise ValueError
        # So I need to update the service too or bypass it here.
        # Actually, let's update the service to be more flexible.
        flow = await flow_service.submit_for_approval(db, flow_id, current_user.id)
        # Re-render status area or the whole card
        return templates.TemplateResponse(request, "flows/partials/flow_card.html", {
            "flow": flow,
            "user": current_user
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/api/v1/admin/flows/{flow_id}/reactivate", summary="Reactivate flow")
async def reactivate_flow_route(
    request: Request,
    flow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.ADMIN)),
):
    """Reactivate an archived flow."""
    try:
        flow = await flow_service.reactivate_flow(db, flow_id, current_user.id)
        if request.headers.get("HX-Request"):
            return templates.TemplateResponse(request, "flows/partials/flow_card.html", {
                "flow": flow,
                "user": current_user
            })
        return RedirectResponse(url=f"/admin/flows/{flow_id}", status_code=303)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/api/v1/admin/flows/{flow_id}/approve", summary="Approve flow")
async def approve_flow_route(
    request: Request,
    flow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.CLINICIAN, Role.ADMIN)),
):
    """Approve and activate a flow."""
    try:
        flow = await flow_service.approve_flow(db, flow_id, current_user.id)
        # Return updated card (replaces existing one if target is card)
        # Or redirect if on detail page
        if request.headers.get("HX-Request"):
            return templates.TemplateResponse(request, "flows/partials/flow_card.html", {
                "flow": flow,
                "user": current_user
            })
        return RedirectResponse(url=f"/admin/flows/{flow_id}", status_code=303)
    except ValueError as e:
        if request.headers.get("HX-Request"):
            return HTMLResponse(content=f'<div class="text-red-400 text-xs p-2">{str(e)}</div>', status_code=400)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/v1/admin/flows/{flow_id}/test", summary="Sandbox test flow")
async def test_flow_sandbox_route(
    request: Request,
    flow_id: uuid.UUID,
    answers_json: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.CLINICIAN, Role.ADMIN)),
):
    """Run a flow sandbox test."""
    flow = await flow_service.get_flow_by_id(db, flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    try:
        answers = json.loads(answers_json)
        result = await flow_service.test_flow_sandbox(flow, answers)
        return templates.TemplateResponse(request, "flows/partials/sandbox_result.html", {
            "result": result
        })
    except json.JSONDecodeError:
        return HTMLResponse(content='<div class="text-red-400 text-xs">Invalid JSON in answers</div>', status_code=400)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error testing flow sandbox")
        return HTMLResponse(content='<div class="text-red-400 text-xs text-center border border-red-400 bg-red-900/20 p-2 rounded">An internal server error occurred.</div>', status_code=400)
