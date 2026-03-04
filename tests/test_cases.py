import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.enums import AuditAction, CaseOutcome, CaseStatus, Role
from app.core.security import create_session_cookie, encrypt_field
from app.modules.audit.models import AuditLog
from app.modules.auth.models import User
from app.modules.cases.models import Case


@pytest.fixture
def student_cookie(test_user):
    return create_session_cookie(str(test_user.id), Role.STUDENT.value)


@pytest.fixture
async def clinician_user(db_session):
    user = User(
        email=f"clinician_{uuid.uuid4().hex[:6]}@example.com",
        role=Role.CLINICIAN,
        auth_provider="supabase",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_case_access_control(client: AsyncClient, db_session, test_user: User, student_cookie, test_flow):
    # 1. Create a case for test_user
    case = Case(
        user_id=test_user.id,
        flow_id=test_flow.id,
        answers_enc="encrypted_val",
        score=10,
        outcome=CaseOutcome.SELF_CARE,
        status=CaseStatus.TRIAGED,
    )
    db_session.add(case)

    # 2. Create another user and their case
    other_user = User(
        email="other@example.com",
        role=Role.STUDENT,
        auth_provider="supabase",
    )
    db_session.add(other_user)
    await db_session.flush()

    other_case = Case(
        user_id=other_user.id,
        flow_id=test_flow.id,
        answers_enc="other_enc",
        score=20,
        outcome=CaseOutcome.CLINIC,
        status=CaseStatus.TRIAGED,
    )
    db_session.add(other_case)
    await db_session.commit()

    # 3. Test self access
    client.cookies.set("session", student_cookie)
    response = await client.get(f"/cases/{case.id}")
    assert response.status_code == 200
    assert "Your Triage Result" in response.text

    # 4. Test forbidden access
    response = await client.get(f"/cases/{other_case.id}")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_clinician_case_list_and_filters(client: AsyncClient, db_session, clinician_user, test_user, test_flow):
    # Create some cases (valid user IDs)
    case1 = Case(
        user_id=test_user.id,
        flow_id=test_flow.id,
        answers_enc="e1",
        outcome=CaseOutcome.EMERGENCY,
        status=CaseStatus.TRIAGED,
    )
    case2 = Case(
        user_id=test_user.id,
        flow_id=test_flow.id,
        answers_enc="e2",
        outcome=CaseOutcome.PHARMACY,
        status=CaseStatus.TRIAGED,
    )
    db_session.add_all([case1, case2])
    await db_session.commit()

    cookie = create_session_cookie(str(clinician_user.id), Role.CLINICIAN.value)
    client.cookies.set("session", cookie)

    # List all
    response = await client.get("/clinician/cases")
    assert response.status_code == 200
    assert "EMERGENCY" in response.text
    assert "PHARMACY" in response.text

    # Filter by outcome
    response = await client.get("/clinician/cases?outcome=EMERGENCY")
    assert response.status_code == 200
    assert "EMERGENCY" in response.text
    # The table should contain EMERGENCY but not the PHARMACY row
    # The filter dropdown will still have PHARMACY, so we look for the badge pattern in table
    assert "bg-red-400" in response.text # EMERGENCY badge
    assert "bg-blue-400" not in response.text # PHARMACY badge should be absent in filtered results


@pytest.mark.asyncio
async def test_case_override_and_audit(client: AsyncClient, db_session, clinician_user, test_user, test_flow):
    case = Case(
        user_id=test_user.id,
        flow_id=test_flow.id,
        answers_enc="encrypted_answers",
        score=10,
        outcome=CaseOutcome.SELF_CARE,
        status=CaseStatus.TRIAGED,
    )
    db_session.add(case)
    await db_session.commit()

    cookie = create_session_cookie(str(clinician_user.id), Role.CLINICIAN.value)
    client.cookies.set("session", cookie)

    # Apply override
    override_data = {
        "new_outcome": "CLINIC",
        "override_note": "Patient exhibits worsening symptoms upon secondary review.",
    }
    response = await client.put(
        f"/api/v1/cases/{case.id}/override",
        data=override_data,
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "Override applied successfully" in response.text

    # Verify DB update
    await db_session.refresh(case)
    assert case.outcome == CaseOutcome.CLINIC
    assert case.status == CaseStatus.OVERRIDDEN
    assert case.override_note == override_data["override_note"]

    # Verify Audit Log
    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.target_id == case.id,
            AuditLog.action == AuditAction.CASE_OVERRIDDEN.value,
        )
    )
    audit = result.scalar_one_or_none()
    assert audit is not None
    assert audit.actor_id == clinician_user.id
    assert audit.diff["after"]["outcome"] == "CLINIC"


@pytest.mark.asyncio
async def test_case_answers_decryption(client: AsyncClient, db_session, clinician_user, test_user, test_flow):
    answers = {"q1": "Yes, I am coughing"}
    enc = encrypt_field(json.dumps(answers))

    case = Case(
        user_id=test_user.id,
        flow_id=test_flow.id,
        answers_enc=enc,
        score=5,
        outcome=CaseOutcome.SELF_CARE,
        status=CaseStatus.TRIAGED,
    )
    db_session.add(case)
    await db_session.commit()

    cookie = create_session_cookie(str(clinician_user.id), Role.CLINICIAN.value)
    client.cookies.set("session", cookie)

    response = await client.get(f"/clinician/cases/{case.id}")
    assert response.status_code == 200
    assert "Yes, I am coughing" in response.text
