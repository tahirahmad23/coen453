from __future__ import annotations

import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import FlowStatus
from app.core.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.modules.auth.models import User
    from app.modules.cases.models import Case

class SymptomFlow(TimestampMixin, Base):
    __tablename__ = "symptom_flows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    rule_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[FlowStatus] = mapped_column(
        SAEnum(FlowStatus), nullable=False, default=FlowStatus.DRAFT, index=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # relationships
    approved_by_user: Mapped[User | None] = relationship(
        "User", back_populates="approved_flows", foreign_keys=[approved_by]
    )
    cases: Mapped[list[Case]] = relationship("Case", back_populates="flow", lazy="select")
