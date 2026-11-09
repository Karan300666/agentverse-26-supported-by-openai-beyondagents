import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.specialty import Specialty


class Doctor(Base):
    __tablename__ = "doctors"
    __table_args__ = (CheckConstraint("consultation_fee >= 0", name="fee_non_negative"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(100))
    specialty_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("specialties.id", ondelete="RESTRICT"),
        index=True,
    )
    consultation_fee: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3), server_default="INR")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    specialty: Mapped[Specialty] = relationship(lazy="joined")