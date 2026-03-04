import pytest
from pydantic import ValidationError

from app.core.enums import CaseOutcome
from app.modules.engine.service import (
    advance,
    calculate_outcome,
    check_red_flags,
    get_node,
    get_start_node,
    validate_flow,
)


@pytest.fixture
def valid_payload() -> dict:
    return {
        "flow_id": "550e8400-e29b-41d4-a716-446655440000",
        "version": 1,
        "red_flags": ["q_chest_pain"],
        "start_node": "q1",
        "nodes": {
            "q1": {
                "type": "question",
                "text": "How long have your symptoms lasted?",
                "hint": "Include today",
                "options": [
                    {"label": "Less than 1 day", "score": 5, "next": "q2"},
                    {"label": "1 to 3 days", "score": 15, "next": "q2"},
                    {"label": "More than 3 days", "score": 30, "next": "outcome_clinic"},
                ],
            },
            "q2": {
                "type": "question",
                "text": "Severity?",
                "options": [
                    {"label": "Mild", "score": 5, "next": "outcome_self_care"},
                    {"label": "Moderate", "score": 20, "next": "outcome_pharmacy"},
                    {"label": "Severe", "score": 40, "next": "q_chest_pain"},
                ],
            },
            "q_chest_pain": {
                "type": "question",
                "text": "Chest pain?",
                "options": [
                    {"label": "Yes", "score": 100, "next": "outcome_emergency"},
                    {"label": "No", "score": 0, "next": "outcome_clinic"},
                ],
            },
            "outcome_self_care": {
                "type": "outcome",
                "result": "SELF_CARE",
                "issue_token": False,
                "message": "Rest.",
            },
            "outcome_pharmacy": {
                "type": "outcome",
                "result": "PHARMACY",
                "issue_token": True,
                "message": "Pharmacy.",
            },
            "outcome_clinic": {
                "type": "outcome",
                "result": "CLINIC",
                "issue_token": False,
                "message": "Clinic.",
            },
            "outcome_emergency": {
                "type": "outcome",
                "result": "EMERGENCY",
                "issue_token": False,
                "message": "Hospital.",
            },
        },
    }


def test_validate_flow_valid(valid_payload) -> None:
    flow = validate_flow(valid_payload)
    assert flow.flow_id == valid_payload["flow_id"]
    assert len(flow.nodes) == 7


def test_validate_flow_invalid_schema() -> None:
    with pytest.raises(ValidationError):
        validate_flow({"invalid": "payload"})


def test_validate_flow_missing_start_node(valid_payload) -> None:
    valid_payload["start_node"] = "non_existent"
    with pytest.raises(ValueError, match="start_node 'non_existent' does not exist"):
        validate_flow(valid_payload)


def test_validate_flow_missing_red_flag(valid_payload) -> None:
    valid_payload["red_flags"] = ["missing_node"]
    with pytest.raises(ValueError, match="red_flag node 'missing_node' does not exist"):
        validate_flow(valid_payload)


def test_validate_flow_missing_option_next(valid_payload) -> None:
    valid_payload["nodes"]["q1"]["options"][0]["next"] = "void"
    with pytest.raises(ValueError, match="points to non-existent node 'void'"):
        validate_flow(valid_payload)


def test_validate_flow_circular_reference(valid_payload) -> None:
    valid_payload["nodes"]["q2"]["options"][0]["next"] = "q1"
    with pytest.raises(ValueError, match="Circular reference detected"):
        validate_flow(valid_payload)


def test_validate_flow_question_no_options(valid_payload) -> None:
    valid_payload["nodes"]["q1"]["options"] = []
    with pytest.raises(ValueError, match="must have at least one option"):
        validate_flow(valid_payload)


def test_get_start_node(valid_payload) -> None:
    flow = validate_flow(valid_payload)
    node = get_start_node(flow)
    assert node.text == "How long have your symptoms lasted?"


def test_get_start_node_outcome(valid_payload) -> None:
    valid_payload["start_node"] = "outcome_self_care"
    flow = validate_flow(valid_payload)
    with pytest.raises(ValueError, match="start_node is an OutcomeNode"):
        get_start_node(flow)


def test_check_red_flags(valid_payload) -> None:
    flow = validate_flow(valid_payload)
    assert check_red_flags(flow, {"q1": "Mild"}) is False
    assert check_red_flags(flow, {"q_chest_pain": "Yes"}) is True


def test_advance_valid(valid_payload) -> None:
    flow = validate_flow(valid_payload)
    next_node_id, score = advance(flow, "q1", "Less than 1 day")
    assert next_node_id == "q2"
    assert score == 5


def test_advance_invalid_node(valid_payload) -> None:
    flow = validate_flow(valid_payload)
    with pytest.raises(ValueError, match="Node 'missing' not found"):
        advance(flow, "missing", "label")


def test_advance_not_question(valid_payload) -> None:
    flow = validate_flow(valid_payload)
    with pytest.raises(ValueError, match="is not a QuestionNode"):
        advance(flow, "outcome_self_care", "label")


def test_advance_invalid_option(valid_payload) -> None:
    flow = validate_flow(valid_payload)
    with pytest.raises(ValueError, match="Option 'Wrong' not found"):
        advance(flow, "q1", "Wrong")


def test_get_node(valid_payload) -> None:
    flow = validate_flow(valid_payload)
    node = get_node(flow, "q1")
    assert node.type == "question"
    with pytest.raises(ValueError, match="Node 'missing' not found"):
        get_node(flow, "missing")


def test_calculate_outcome_self_care(valid_payload) -> None:
    flow = validate_flow(valid_payload)
    answers = {"q1": "Less than 1 day", "q2": "Mild"}
    outcome, score, flagged = calculate_outcome(flow, answers)
    assert outcome == CaseOutcome.SELF_CARE
    assert score == 10
    assert flagged is False


def test_calculate_outcome_pharmacy(valid_payload) -> None:
    flow = validate_flow(valid_payload)
    answers = {"q1": "1 to 3 days", "q2": "Moderate"}
    outcome, score, flagged = calculate_outcome(flow, answers)
    assert outcome == CaseOutcome.PHARMACY
    assert score == 35
    assert flagged is False


def test_calculate_outcome_emergency(valid_payload) -> None:
    flow = validate_flow(valid_payload)
    answers = {"q1": "Less than 1 day", "q2": "Severe", "q_chest_pain": "Yes"}
    outcome, score, flagged = calculate_outcome(flow, answers)
    assert outcome == CaseOutcome.EMERGENCY
    assert score == 145
    assert flagged is True


def test_calculate_outcome_missing_answer(valid_payload) -> None:
    flow = validate_flow(valid_payload)
    answers = {"q1": "Less than 1 day"}
    with pytest.raises(ValueError, match="Missing answer for node 'q2'"):
        calculate_outcome(flow, answers)


def test_calculate_outcome_invalid_answer(valid_payload) -> None:
    flow = validate_flow(valid_payload)
    answers = {"q1": "Wrong"}
    with pytest.raises(ValueError, match="Invalid answer 'Wrong'"):
        calculate_outcome(flow, answers)
