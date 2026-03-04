import uuid
import json
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import select, func
from app.core.enums import FlowStatus, Role, AuditAction
from app.modules.flows import service as flow_service
from app.modules.flows.models import SymptomFlow

@pytest.fixture
def sample_rule_payload():
    return {
        "flow_id": str(uuid.uuid4()),
        "version": 1,
        "red_flags": [],
        "start_node": "q1",
        "nodes": {
            "q1": {
                "type": "question",
                "text": "Test?",
                "options": [{"label": "Yes", "score": 10, "next": "o1"}]
            },
            "o1": {
                "type": "outcome",
                "result": "SELF_CARE",
                "issue_token": False,
                "message": "Done"
            }
        }
    }

@pytest.mark.asyncio
async def test_create_flow_valid(db_session, admin_user, sample_rule_payload):
    """Valid payload creates a DRAFT flow."""
    flow = await flow_service.create_flow(db_session, "Test Flow", sample_rule_payload, admin_user.id)
    assert flow.name == "Test Flow"
    assert flow.status == FlowStatus.DRAFT
    assert flow.version == 1

@pytest.mark.asyncio
async def test_create_flow_version_increment(db_session, admin_user, sample_rule_payload):
    """Subsequent flows with same name increment version."""
    await flow_service.create_flow(db_session, "Multi Version", sample_rule_payload, admin_user.id)
    flow2 = await flow_service.create_flow(db_session, "Multi Version", sample_rule_payload, admin_user.id)
    assert flow2.version == 2

@pytest.mark.asyncio
async def test_submit_for_approval(db_session, admin_user, sample_rule_payload):
    """Creator can submit a DRAFT flow for approval."""
    flow = await flow_service.create_flow(db_session, "To Submit", sample_rule_payload, admin_user.id)
    updated = await flow_service.submit_for_approval(db_session, flow.id, admin_user.id)
    assert updated.status == FlowStatus.PENDING_APPROVAL

@pytest.mark.asyncio
async def test_approve_flow_success(db_session, admin_user, clinician_user, sample_rule_payload):
    """Clinician can approve a PENDING flow. Prev active flow is archived."""
    # 1. Create and make one flow ACTIVE
    flow1 = await flow_service.create_flow(db_session, "Flow 1", sample_rule_payload, admin_user.id)
    flow1.status = FlowStatus.ACTIVE
    await db_session.commit()
    
    # 2. Create another and submit
    flow2 = await flow_service.create_flow(db_session, "Flow 2", sample_rule_payload, admin_user.id)
    await flow_service.submit_for_approval(db_session, flow2.id, admin_user.id)
    
    # 3. Approve with DIFFERENT user (clinician)
    with patch("app.modules.flows.service.redis_delete", new_callable=AsyncMock):
        approved = await flow_service.approve_flow(db_session, flow2.id, clinician_user.id)
        
    assert approved.status == FlowStatus.ACTIVE
    assert approved.approved_by == clinician_user.id
    
    # Verify flow1 is archived
    await db_session.refresh(flow1)
    assert flow1.status == FlowStatus.ARCHIVED

@pytest.mark.asyncio
async def test_approve_flow_self_approval_fails(db_session, admin_user, sample_rule_payload):
    """Creator CANNOT approve their own flow."""
    flow = await flow_service.create_flow(db_session, "Self Approval", sample_rule_payload, admin_user.id)
    await flow_service.submit_for_approval(db_session, flow.id, admin_user.id)
    
    with pytest.raises(ValueError, match="Separation of duties"):
        await flow_service.approve_flow(db_session, flow.id, admin_user.id)

@pytest.mark.asyncio
async def test_get_active_flow_caching(db_session, admin_user, sample_rule_payload):
    """get_active_flow uses Redis cache."""
    flow = await flow_service.create_flow(db_session, "Active Flow", sample_rule_payload, admin_user.id)
    flow.status = FlowStatus.ACTIVE
    await db_session.commit()
    
    # Partial mock of redis
    with patch("app.modules.flows.service.redis_get_str", new_callable=AsyncMock) as mock_get, \
         patch("app.modules.flows.service.redis_set", new_callable=AsyncMock) as mock_set:
        
        # 1. Cache miss
        mock_get.return_value = None
        result1 = await flow_service.get_active_flow(db_session)
        assert result1.id == flow.id
        mock_set.assert_called_once()
        
        # 2. Cache hit
        mock_get.return_value = json.dumps({"id": str(flow.id)})
        result2 = await flow_service.get_active_flow(db_session)
        assert result2.id == flow.id

@pytest.mark.asyncio
async def test_sandbox_no_persistence(db_session, admin_user, sample_rule_payload):
    """Sandbox test returns result without creating DB records."""
    flow = await flow_service.create_flow(db_session, "Sandbox", sample_rule_payload, admin_user.id)
    
    from app.modules.cases.models import Case
    from sqlalchemy import func
    
    count_before = (await db_session.execute(select(func.count(Case.id)))).scalar()
    
    result = await flow_service.test_flow_sandbox(flow, {"q1": "Yes"})
    assert result["outcome"] == "SELF_CARE"
    assert "q1" in result["path_taken"]
    
    count_after = (await db_session.execute(select(func.count(Case.id)))).scalar()
    assert count_before == count_after
