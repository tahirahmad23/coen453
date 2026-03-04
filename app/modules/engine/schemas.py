from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.core.enums import CaseOutcome


class Option(BaseModel):
    label: str
    score: int
    next: str


class QuestionNode(BaseModel):
    type: Literal["question"]
    text: str
    hint: str | None = None
    options: list[Option]


class PrescriptionItem(BaseModel):
    name: str                          # e.g. "Paracetamol 500mg"
    dose: str                          # e.g. "1-2 tablets every 4-6 hours"
    instructions: str | None = None   # e.g. "Take with food", "Max 8 tablets/day"


class OutcomeNode(BaseModel):
    type: Literal["outcome"]
    result: CaseOutcome
    issue_token: bool = False
    message: str | None = None
    prescriptions: list[PrescriptionItem] = []  # drug/treatment recommendations


Node = Annotated[QuestionNode | OutcomeNode, Field(discriminator="type")]


class RulePayload(BaseModel):
    flow_id: str
    version: int
    red_flags: list[str]
    start_node: str
    nodes: dict[str, Node]
