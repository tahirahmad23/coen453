import pytest
import uuid
from io import BytesIO
from sqlalchemy import select
from app.modules.integrations import service as integration_service
from app.modules.cases.models import Case
from app.modules.auth.models import User
from app.core.enums import CaseOutcome, CaseStatus

@pytest.fixture
def valid_csv():
    # student_id, outcome, visit_date, notes
    content = "student_id,outcome,visit_date,notes\n"
    content += "STU001,PHARMACY,2024-01-15T10:00:00,Standard cold\n"
    content += "STU001,CLINIC,2024-02-20T14:30:00,Fever symptoms\n"
    return content.encode("utf-8")

@pytest.mark.asyncio
async def test_import_hospital_csv_success(db_session, admin_user, student_user, valid_csv):
    """Valid CSV imports cases and maps to existing students."""
    # Ensure student has correct student_id (from conftest usually)
    student_user.student_id = "STU001"
    await db_session.commit()
    await db_session.refresh(student_user)
    
    summary = await integration_service.import_hospital_csv(db_session, valid_csv, admin_user.id)
    
    assert summary["total"] == 2
    assert summary["imported"] == 2
    assert summary["skipped"] == 0
    
    # Check DB
    result = await db_session.execute(select(Case).where(Case.user_id == student_user.id))
    cases = result.scalars().all()
    assert len(cases) == 2
    assert all(c.status == CaseStatus.CLOSED for c in cases)
    assert all(c.answers_enc == "HISTORICAL_IMPORT" for c in cases)
    assert all(c.flow_id is None for c in cases)
    assert cases[0].notes == "Standard cold"

@pytest.mark.asyncio
async def test_import_hospital_csv_skips_bad_rows(db_session, admin_user, student_user):
    """Invalid outcomes or missing students are skipped with errors recorded."""
    student_user.student_id = "REAL_STU"
    await db_session.commit()
    await db_session.refresh(student_user)
    
    content = "student_id,outcome,visit_date,notes\n"
    content += "REAL_STU,INVALID_OUTCOME,2024-01-15,Bad outcome\n"
    content += "GHOST_STU,PHARMACY,2024-01-15,Missing student\n"
    content += "REAL_STU,SELF_CARE,NOT_A_DATE,Bad date\n"
    csv_bytes = content.encode("utf-8")
    
    summary = await integration_service.import_hospital_csv(db_session, csv_bytes, admin_user.id)
    
    assert summary["total"] == 3
    assert summary["imported"] == 0
    assert summary["skipped"] == 3
    assert len(summary["errors"]) == 3
    assert "Invalid outcome" in summary["errors"][0]
    assert "not found" in summary["errors"][1]
    assert "Invalid date format" in summary["errors"][2]

@pytest.mark.asyncio
async def test_import_hospital_csv_too_many_rows(db_session, admin_user):
    """Import rejects files with > 1000 rows."""
    content = "student_id,outcome,visit_date,notes\n"
    content += "STU,SELF_CARE,2024-01-01,test\n" * 1001
    csv_bytes = content.encode("utf-8")
    
    with pytest.raises(ValueError, match="maximum limit of 1000 rows"):
        await integration_service.import_hospital_csv(db_session, csv_bytes, admin_user.id)
