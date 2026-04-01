from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.enums import Role
from app.core.templates import templates
from app.modules.auth.schemas import UserContext
from app.modules.integrations import service as integration_service

router = APIRouter(prefix="", tags=["integrations"])


@router.get("/admin/import", summary="View data import page")
async def view_import_page(
    request: Request,
    current_user: UserContext = Depends(require_role(Role.ADMIN)),
):
    """Render the hospital data import page."""
    return templates.TemplateResponse(request, "integrations/import_csv.html", {
        "user": current_user
    })


@router.post("/api/v1/integrations/import", summary="Import hospital CSV data")
async def import_csv_route(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(require_role(Role.ADMIN)),
):
    """
    Accept CSV file upload and import as historical cases.
    Returns the summary on the same page.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=422, detail="File must be a CSV.")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:  # 5MB
        raise HTTPException(status_code=413, detail="File too large. Max 5MB.")

    try:
        summary = await integration_service.import_hospital_csv(db, content, current_user.id)
        return templates.TemplateResponse(request, "integrations/import_csv.html", {
            "summary": summary,
            "user": current_user
        })
    except ValueError as e:
        return templates.TemplateResponse(request, "integrations/import_csv.html", {
            "error": str(e),
            "user": current_user
        }, status_code=400)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error importing CSV")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")
