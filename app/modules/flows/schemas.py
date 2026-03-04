from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class FlowCreateRequest(BaseModel):
    name: str
    rule_payload: dict


class SandboxTestRequest(BaseModel):
    answers: dict[str, str]


class FlowResponse(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    status: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)
