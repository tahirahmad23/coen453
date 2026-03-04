from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import CaseOutcome, CaseStatus


class CaseCreateRequest(BaseModel):
    """Internal schema — called by engine routes, not directly by browser forms."""
    flow_id: uuid.UUID
    answers: dict[str, str]    # {node_id: option_label}
    score: int
    outcome: CaseOutcome
    is_flagged: bool
    duration_secs: int | None

class CaseResponse(BaseModel):
    id: uuid.UUID
    outcome: CaseOutcome | None
    status: CaseStatus
    score: int
    is_flagged: bool
    override_note: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class CaseListResponse(BaseModel):
    cases: list[CaseResponse]
    total: int
    page: int
    page_size: int

class CaseOverrideRequest(BaseModel):
    new_outcome: CaseOutcome
    override_note: str = Field(..., min_length=10, max_length=1000)
