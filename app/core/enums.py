from __future__ import annotations

import enum


class Role(enum.StrEnum):
    STUDENT = "student"
    CLINICIAN = "clinician"
    PHARMACIST = "pharmacist"
    ADMIN = "admin"

class FlowStatus(enum.StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    ARCHIVED = "archived"

class CaseOutcome(enum.StrEnum):
    SELF_CARE = "SELF_CARE"
    PHARMACY = "PHARMACY"
    CLINIC = "CLINIC"
    EMERGENCY = "EMERGENCY"

class CaseStatus(enum.StrEnum):
    PENDING = "PENDING"
    TRIAGED = "TRIAGED"
    OVERRIDDEN = "OVERRIDDEN"
    CLOSED = "CLOSED"

class AuditAction(enum.StrEnum):
    USER_CREATED = "USER_CREATED"
    USER_LOGIN = "USER_LOGIN"
    CASE_CREATED = "CASE_CREATED"
    CASE_OVERRIDDEN = "CASE_OVERRIDDEN"
    TOKEN_ISSUED = "TOKEN_ISSUED"
    TOKEN_USED = "TOKEN_USED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    FLOW_CREATED = "FLOW_CREATED"
    FLOW_APPROVED = "FLOW_APPROVED"
    FLOW_ARCHIVED = "FLOW_ARCHIVED"
    FLOW_SUBMITTED = "FLOW_SUBMITTED"
    IMPORT_STARTED = "IMPORT_STARTED"
    IMPORT_COMPLETED = "IMPORT_COMPLETED"

class TargetType(enum.StrEnum):
    USER = "user"
    CASE = "case"
    TOKEN = "token"
    FLOW = "flow"
    IMPORT = "import"
