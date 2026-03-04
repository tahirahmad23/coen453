import datetime
import json
import logging
import uuid
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CaseOutcome, FlowStatus, AuditAction, TargetType
from app.core.redis import redis_set, redis_get_str, redis_delete
from app.modules.engine.service import calculate_outcome, validate_flow
from app.modules.flows.models import SymptomFlow
from app.modules.flows.schemas import FlowCreateRequest
from app.modules.audit.service import log

logger = logging.getLogger(__name__)

ACTIVE_FLOW_CACHE_KEY = "active_flow"
ACTIVE_FLOW_TTL = 300  # 5 minutes


async def get_active_flow(db: AsyncSession) -> SymptomFlow | None:
    """Return the currently active flow, with Redis caching."""
    # Try cache first
    cached = await redis_get_str(ACTIVE_FLOW_CACHE_KEY)
    if cached:
        try:
            flow_data = json.loads(cached)
            flow_id = uuid.UUID(flow_data["id"])
            result = await db.execute(select(SymptomFlow).where(SymptomFlow.id == flow_id))
            flow = result.scalar_one_or_none()
            if flow and flow.status == FlowStatus.ACTIVE:
                return flow
        except (json.JSONDecodeError, ValueError, KeyError):
            logger.warning("Redis cache for active_flow is malformed, ignoring.")

    # Cache miss or invalid - query DB
    result = await db.execute(
        select(SymptomFlow).where(SymptomFlow.status == FlowStatus.ACTIVE).limit(1)
    )
    flow = result.scalar_one_or_none()

    if flow:
        await redis_set(
            ACTIVE_FLOW_CACHE_KEY,
            json.dumps({"id": str(flow.id)}),
            ACTIVE_FLOW_TTL
        )
    return flow


async def create_flow(db: AsyncSession, name: str, rule_payload_raw: str | dict, created_by_id: uuid.UUID) -> SymptomFlow:
    """Validate and create a new draft flow."""
    # 1. Parse payload
    if isinstance(rule_payload_raw, str):
        try:
            rule_payload = json.loads(rule_payload_raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {str(e)}")
    else:
        rule_payload = rule_payload_raw

    # 2. engine.validate_flow() - raises ValidationError if invalid
    validated_rule = validate_flow(rule_payload)
    
    # 3. Determine next version number
    result = await db.execute(
        select(func.max(SymptomFlow.version))
        .where(SymptomFlow.name == name)
    )
    max_version = result.scalar() or 0
    
    # 4. Insert SymptomFlow
    flow = SymptomFlow(
        name=name,
        version=max_version + 1,
        rule_payload=validated_rule.model_dump(),
        status=FlowStatus.DRAFT,
        created_by=created_by_id,
    )
    db.add(flow)
    await db.flush() # Get ID before audit log
    
    # 5. Write audit
    await log(
        db,
        actor_id=created_by_id,
        action=AuditAction.FLOW_CREATED,
        target_type=TargetType.FLOW,
        target_id=flow.id,
        diff={"name": name, "version": flow.version}
    )
    
    await db.commit()
    await db.refresh(flow)
    return flow


async def submit_for_approval(db: AsyncSession, flow_id: uuid.UUID, submitted_by_id: uuid.UUID) -> SymptomFlow:
    """Transition DRAFT to PENDING_APPROVAL."""
    result = await db.execute(select(SymptomFlow).where(SymptomFlow.id == flow_id))
    flow = result.scalar_one_or_none()
    
    if not flow:
        raise ValueError("Flow not found")
    # Transition DRAFT to PENDING_APPROVAL
    flow.status = FlowStatus.PENDING_APPROVAL
    
    await log(
        db,
        actor_id=submitted_by_id,
        action=AuditAction.FLOW_SUBMITTED,
        target_type=TargetType.FLOW,
        target_id=flow.id
    )
    
    await db.commit()
    await db.refresh(flow)
    return flow


async def approve_flow(db: AsyncSession, flow_id: uuid.UUID, approved_by_id: uuid.UUID) -> SymptomFlow:
    """
    Approve flow: Archive current active flow and set this one to ACTIVE.
    Must be atomic with SELECT FOR UPDATE.
    """
    # 1. Fetch flow with lock
    result = await db.execute(
        select(SymptomFlow).where(SymptomFlow.id == flow_id).with_for_update()
    )
    flow = result.scalar_one_or_none()
    
    if not flow:
        raise ValueError("Flow not found")
    if flow.status != FlowStatus.PENDING_APPROVAL:
        raise ValueError(f"Cannot approve flow in {flow.status} status")
    if flow.created_by == approved_by_id:
        raise ValueError("Separation of duties: Creator cannot approve their own flow")
        
    # 2. Fetch currently ACTIVE flow and archive it
    active_result = await db.execute(
        select(SymptomFlow).where(SymptomFlow.status == FlowStatus.ACTIVE).with_for_update()
    )
    current_active = active_result.scalars().all()
    
    for old_flow in current_active:
        old_flow.status = FlowStatus.ARCHIVED
        await log(
            db,
            actor_id=approved_by_id,
            action=AuditAction.FLOW_ARCHIVED,
            target_type=TargetType.FLOW,
            target_id=old_flow.id
        )

    # 3. Set new status
    flow.status = FlowStatus.ACTIVE
    flow.approved_by = approved_by_id
    flow.approved_at = datetime.datetime.now(datetime.UTC)
    
    await log(
        db,
        actor_id=approved_by_id,
        action=AuditAction.FLOW_APPROVED,
        target_type=TargetType.FLOW,
        target_id=flow.id
    )
    
    # 4. Invalidate cache
    await redis_delete(ACTIVE_FLOW_CACHE_KEY)
    
    await db.commit()
    await db.refresh(flow)
    return flow


async def test_flow_sandbox(flow: SymptomFlow, answers: dict[str, str]) -> dict:
    """Run engine calculations without creating DB records or audit log."""
    from app.modules.engine.schemas import RulePayload
    from app.modules.engine.service import calculate_outcome, get_node, get_start_node, advance
    
    rule = RulePayload.model_validate(flow.rule_payload)
    
    # 1. Calculate outcome
    outcome, score, flagged = calculate_outcome(rule, answers)
    
    # 2. Reconstruct path for sandbox visualization
    path_taken = []
    current_node_id = rule.start_node
    path_taken.append(current_node_id)
    
    node = get_node(rule, current_node_id)
    while node.type == "question":
        ans = answers.get(current_node_id)
        if not ans:
            break
        try:
            next_node_id, _ = advance(rule, current_node_id, ans)
            path_taken.append(next_node_id)
            current_node_id = next_node_id
            node = get_node(rule, current_node_id)
        except ValueError:
            break
            
    return {
        "outcome": outcome.value,
        "score": score,
        "is_flagged": flagged,
        "path_taken": path_taken
    }


async def get_flow_by_id(db: AsyncSession, flow_id: uuid.UUID) -> SymptomFlow | None:
    """Return a flow by ID."""
    result = await db.execute(select(SymptomFlow).where(SymptomFlow.id == flow_id))
    return result.scalar_one_or_none()


async def list_flows(db: AsyncSession, status_filter: str | None = None) -> list[SymptomFlow]:
    """List all flows, optionally filtered by status."""
    query = select(SymptomFlow)
    if status_filter:
        query = query.where(SymptomFlow.status == status_filter)
    query = query.order_by(SymptomFlow.created_at.desc())
    
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_flow(
    db: AsyncSession, 
    flow_id: uuid.UUID, 
    name: str, 
    rule_payload_raw: str | dict,
    actor_id: uuid.UUID
) -> SymptomFlow:
    """Update an existing DRAFT flow."""
    flow = await get_flow_by_id(db, flow_id)
    if not flow:
        raise ValueError("Flow not found")
    if flow.status not in [FlowStatus.DRAFT, FlowStatus.ARCHIVED]:
        raise ValueError(f"Flows in {flow.status} status cannot be edited")
    
    # Parse and validate
    if isinstance(rule_payload_raw, str):
        try:
            rule_payload = json.loads(rule_payload_raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {str(e)}")
    else:
        rule_payload = rule_payload_raw

    validated_rule = validate_flow(rule_payload)
    
    # Track diff for audit
    diff = {}
    if flow.name != name:
        diff["name"] = {"old": flow.name, "new": name}
    
    flow.name = name
    flow.rule_payload = validated_rule.model_dump()
    
    await log(
        db,
        actor_id=actor_id,
        action=AuditAction.FLOW_CREATED, # Re-using created or could add FLOW_UPDATED
        target_type=TargetType.FLOW,
        target_id=flow.id,
        diff=diff
    )
    
    await db.commit()
    await db.refresh(flow)
    return flow


async def delete_flow(db: AsyncSession, flow_id: uuid.UUID, actor_id: uuid.UUID) -> bool:
    """Delete a flow. Blocks deletion of ACTIVE flows."""
    flow = await get_flow_by_id(db, flow_id)
    if not flow:
        return False
    
    if flow.status == FlowStatus.ACTIVE:
        raise ValueError("Cannot delete an ACTIVE flow. Archive it first.")
    
    await db.delete(flow)
    
    await log(
        db,
        actor_id=actor_id,
        action=AuditAction.FLOW_ARCHIVED, # Re-using archived as a "removed" state for audit
        target_type=TargetType.FLOW,
        target_id=flow_id
    )
    
    await db.commit()
    return True


async def reactivate_flow(db: AsyncSession, flow_id: uuid.UUID, actor_id: uuid.UUID) -> SymptomFlow:
    """
    Reactivate an ARCHIVED flow: Archive current active flow and set this one to ACTIVE.
    """
    # 1. Fetch flow with lock
    result = await db.execute(
        select(SymptomFlow).where(SymptomFlow.id == flow_id).with_for_update()
    )
    flow = result.scalar_one_or_none()
    
    if not flow:
        raise ValueError("Flow not found")
    if flow.status != FlowStatus.ARCHIVED:
        raise ValueError(f"Cannot reactivate flow in {flow.status} status")
        
    # 2. Fetch currently ACTIVE flow and archive it
    active_result = await db.execute(
        select(SymptomFlow).where(SymptomFlow.status == FlowStatus.ACTIVE).with_for_update()
    )
    current_active = active_result.scalars().all()
    
    for old_flow in current_active:
        old_flow.status = FlowStatus.ARCHIVED
        await log(
            db,
            actor_id=actor_id,
            action=AuditAction.FLOW_ARCHIVED,
            target_type=TargetType.FLOW,
            target_id=old_flow.id
        )

    # 3. Set new status
    flow.status = FlowStatus.ACTIVE
    flow.approved_by = actor_id
    flow.approved_at = datetime.datetime.now(datetime.UTC)
    
    await log(
        db,
        actor_id=actor_id,
        action=AuditAction.FLOW_APPROVED, # Using approved as reactivation is a form of approval
        target_type=TargetType.FLOW,
        target_id=flow.id,
        diff={"reactivated_from": "ARCHIVED"}
    )
    
    # 4. Invalidate cache
    await redis_delete(ACTIVE_FLOW_CACHE_KEY)
    
    await db.commit()
    await db.refresh(flow)
    return flow
