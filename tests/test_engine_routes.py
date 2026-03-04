import pytest
from httpx import AsyncClient
from app.core.enums import FlowStatus, CaseOutcome, Role
from app.modules.flows.models import SymptomFlow
from app.modules.auth.models import User
from app.core.security import create_session_cookie

@pytest.fixture
def triage_rule():
    return {
        "flow_id": "test-flow",
        "version": 1,
        "red_flags": ["q_emergency"],
        "start_node": "q1",
        "nodes": {
            "q1": {
                "type": "question",
                "text": "Are you sick?",
                "options": [
                    {"label": "Yes", "score": 10, "next": "outcome_clinic"},
                    {"label": "No", "score": 0, "next": "outcome_self_care"},
                    {"label": "Bad", "score": 50, "next": "q_emergency"}
                ]
            },
            "q_emergency": {
                "type": "question",
                "text": "Chest pain?",
                "options": [
                    {"label": "Yes", "score": 100, "next": "outcome_emergency"},
                    {"label": "No", "score": 0, "next": "outcome_clinic"}
                ]
            },
            "outcome_self_care": {"type": "outcome", "result": "SELF_CARE"},
            "outcome_clinic": {"type": "outcome", "result": "CLINIC"},
            "outcome_emergency": {"type": "outcome", "result": "EMERGENCY"}
        }
    }

@pytest.mark.asyncio
async def test_triage_flow_e2e(client: AsyncClient, db_session, test_user: User, triage_rule):
    # 1. Setup active flow
    flow = SymptomFlow(
        name="Test Flow",
        version=1,
        rule_payload=triage_rule,
        status=FlowStatus.ACTIVE,
        created_by=test_user.id
    )
    db_session.add(flow)
    await db_session.commit()

    # 2. Login (simulate by setting cookie)
    session_cookie = create_session_cookie(str(test_user.id), Role.STUDENT.value)
    client.cookies.set("session", session_cookie)

    # 3. Start triage
    response = await client.get("/triage")
    assert response.status_code == 200
    assert "Are you sick?" in response.text

    # 4. Submit answer (HTMX)
    response = await client.post(
        "/api/v1/engine/answer",
        data={"node_id": "q1", "option_label": "Yes"},
        headers={"HX-Request": "true"}
    )
    if response.status_code != 200:
        pytest.fail(f"Post failed {response.status_code}: {response.text}")
        
    # It should redirect to outcome since next is outcome_clinic
    assert response.headers.get("HX-Redirect", "").startswith("/cases/")

    # 5. Verify case creation
    case_id = response.headers["HX-Redirect"].split("/")[-1]
    from app.modules.cases.models import Case
    case = await db_session.get(Case, case_id)
    assert case is not None
    assert case.outcome == CaseOutcome.CLINIC


@pytest.mark.asyncio
async def test_triage_red_flag_e2e(client: AsyncClient, db_session, test_user: User, triage_rule):
    flow = SymptomFlow(
        name="Emergency Flow",
        version=2,
        rule_payload=triage_rule,
        status=FlowStatus.ACTIVE,
        created_by=test_user.id
    )
    db_session.add(flow)
    await db_session.commit()

    session_cookie = create_session_cookie(str(test_user.id), Role.STUDENT.value)
    client.cookies.set("session", session_cookie)

    # Submit answer that hits red flag
    await client.get("/triage")
    response = await client.post(
        "/api/v1/engine/answer",
        data={"node_id": "q1", "option_label": "Bad"},
        headers={"HX-Request": "true"}
    )
    if response.status_code != 200:
        pytest.fail(f"Step 1 failed {response.status_code}: {response.text}")
        
    assert "Chest pain?" in response.text

    # Submit answer from red flag node
    response = await client.post(
        "/api/v1/engine/answer",
        data={"node_id": "q_emergency", "option_label": "No"},
        headers={"HX-Request": "true"}
    )
    if response.status_code != 200:
        pytest.fail(f"Step 2 failed {response.status_code}: {response.text}")
        
    assert response.headers["HX-Redirect"].startswith("/cases/")
    
    case_id = response.headers["HX-Redirect"].split("/")[-1]
    from app.modules.cases.models import Case
    case = await db_session.get(Case, case_id)
    assert case.outcome == CaseOutcome.EMERGENCY
    assert case.is_flagged is True


@pytest.mark.asyncio
async def test_triage_no_active_flow(client: AsyncClient, test_user: User):
    session_cookie = create_session_cookie(str(test_user.id), Role.STUDENT.value)
    client.cookies.set("session", session_cookie)

    response = await client.get("/triage")
    assert response.status_code == 200
    assert "Triage System is Offline" in response.text
