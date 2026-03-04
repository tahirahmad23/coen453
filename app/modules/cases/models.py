from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import CaseOutcome, CaseStatus
from app.core.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.modules.auth.models import User
    from app.modules.flows.models import SymptomFlow
    from app.modules.tokens.models import PrescriptionToken

class Case(TimestampMixin, Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    flow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("symptom_flows.id"), nullable=True
    )
    answers_enc: Mapped[str] = mapped_column(Text, nullable=False)     # AES-256 encrypted JSON
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    outcome: Mapped[CaseOutcome | None] = mapped_column(SAEnum(CaseOutcome), nullable=True, index=True)
    status: Mapped[CaseStatus] = mapped_column(
        SAEnum(CaseStatus), nullable=False, default=CaseStatus.PENDING, index=True
    )
    is_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    override_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    duration_secs: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # relationships
    user: Mapped[User] = relationship("User", back_populates="cases", foreign_keys="Case.user_id")
    flow: Mapped[SymptomFlow] = relationship("SymptomFlow", back_populates="cases")
    token: Mapped[PrescriptionToken | None] = relationship(
        "PrescriptionToken", back_populates="case", uselist=False
    )
