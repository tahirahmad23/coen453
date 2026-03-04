from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import Role
from app.core.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.modules.cases.models import Case
    from app.modules.flows.models import SymptomFlow

class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    role: Mapped[Role] = mapped_column(SAEnum(Role), nullable=False, default=Role.STUDENT)
    auth_provider: Mapped[str] = mapped_column(String(20), nullable=False, default="email")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # relationships (using strings to avoid circular imports)
    cases: Mapped[list[Case]] = relationship(
        "Case", back_populates="user", lazy="select", foreign_keys="Case.user_id"
    )
    approved_flows: Mapped[list[SymptomFlow]] = relationship(
        "SymptomFlow", back_populates="approved_by_user",
        foreign_keys="SymptomFlow.approved_by", lazy="select"
    )
