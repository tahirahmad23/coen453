from __future__ import annotations

from pydantic import ValidationError

from app.core.enums import CaseOutcome
from app.modules.engine.schemas import OutcomeNode, QuestionNode, RulePayload


def validate_flow(rule_payload: dict) -> RulePayload:
    """
    Parse and validate a raw dict against the RulePayload schema.
    Raises ValidationError if the payload is malformed or logically inconsistent.
    """
    try:
        flow = RulePayload.model_validate(rule_payload)
    except ValidationError as e:
        raise e

    # 1. Existence checks
    if flow.start_node not in flow.nodes:
        raise ValueError(f"start_node '{flow.start_node}' does not exist in nodes")

    for node_id in flow.red_flags:
        if node_id not in flow.nodes:
            raise ValueError(f"red_flag node '{node_id}' does not exist in nodes")

    for node_id, node in flow.nodes.items():
        if isinstance(node, QuestionNode):
            for option in node.options:
                if option.next not in flow.nodes:
                    raise ValueError(
                        f"Node '{node_id}' points to non-existent node '{option.next}'"
                    )

    # 2. Graph analysis (Circular refs and Terminal checks)
    visited = set()
    recursion_stack = set()

    def dfs(node_id: str) -> None:
        if node_id in recursion_stack:
            raise ValueError(f"Circular reference detected at node '{node_id}'")
        if node_id in visited:
            return

        visited.add(node_id)
        recursion_stack.add(node_id)

        node = flow.nodes[node_id]
        if isinstance(node, QuestionNode):
            if not node.options:
                raise ValueError(f"QuestionNode '{node_id}' must have at least one option")
            for option in node.options:
                dfs(option.next)
        
        recursion_stack.remove(node_id)

    # Start DFS from all reachable nodes from the start_node
    dfs(flow.start_node)

    return flow


def get_start_node(flow: RulePayload) -> QuestionNode:
    """Return the first question node."""
    node = flow.nodes[flow.start_node]
    if isinstance(node, OutcomeNode):
        # This is a weird edge case but possible
        raise ValueError("start_node is an OutcomeNode, not a QuestionNode")
    return node


def check_red_flags(flow: RulePayload, answers: dict[str, str]) -> bool:
    """
    Return True if any answered node ID is in flow.red_flags.
    answers: dict of {node_id: option_label}
    """
    for node_id in answers:
        if node_id in flow.red_flags:
            # We also need to check if the answer was "Yes" or equivalent?
            # The prompt says: "node IDs that immediately produce EMERGENCY"
            # In the sample, "q_chest_pain" is in red_flags.
            # If the student reaches q_chest_pain, is it a red flag? 
            # Or only if they answer "Yes"?
            # Task doc says: "node IDs that immediately produce EMERGENCY"
            # It doesn't detail answer-specific red flags in the metadata.
            # Usually, if a node is a red flag, reaching it or answering it is critical.
            # I'll stick to the "node ID exists in answers" logic.
            return True
    return False


def advance(
    flow: RulePayload,
    current_node_id: str,
    selected_option_label: str,
) -> tuple[str, int]:
    """
    Given the current node ID and the selected option label,
    return (next_node_id, score_delta).
    """
    node = flow.nodes.get(current_node_id)
    if not node:
        raise ValueError(f"Node '{current_node_id}' not found")
    
    if not isinstance(node, QuestionNode):
        raise ValueError(f"Node '{current_node_id}' is not a QuestionNode")

    for option in node.options:
        if option.label == selected_option_label:
            return option.next, option.score
            
    raise ValueError(f"Option '{selected_option_label}' not found in node '{current_node_id}'")


def get_node(flow: RulePayload, node_id: str) -> QuestionNode | OutcomeNode:
    """Return the node for a given ID."""
    node = flow.nodes.get(node_id)
    if not node:
        raise ValueError(f"Node '{node_id}' not found")
    return node


def calculate_outcome(
    flow: RulePayload,
    answers: dict[str, str],
) -> tuple[CaseOutcome, int, bool]:
    """
    Walk the full flow from start to end using provided answers.
    Returns: (outcome, total_score, is_flagged)
    """
    current_node_id = flow.start_node
    total_score = 0
    is_flagged = False
    
    # Check initial red flags if we pre-calculate? 
    # Or as we walk? The walk reaches nodes.
    
    while True:
        if current_node_id in flow.red_flags:
            is_flagged = True
        
        node = flow.nodes[current_node_id]
        
        if isinstance(node, OutcomeNode):
            # If we hit an OutcomeNode, we are done. 
            # But wait, what if a red flag was hit? 
            # calculate_outcome documentation says: (outcome, total_score, is_flagged)
            # "Path hitting red_flag returns EMERGENCY" in sample tests.
            if is_flagged:
                return CaseOutcome.EMERGENCY, total_score, True
            return node.result, total_score, is_flagged
            
        # It's a QuestionNode
        answer = answers.get(current_node_id)
        if not answer:
            raise ValueError(f"Missing answer for node '{current_node_id}'")
            
        found_option = False
        for option in node.options:
            if option.label == answer:
                total_score += option.score
                current_node_id = option.next
                found_option = True
                break
        
        if not found_option:
            raise ValueError(f"Invalid answer '{answer}' for node '{current_node_id}'")
