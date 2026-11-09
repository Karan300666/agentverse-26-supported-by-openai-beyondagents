import uuid
from datetime import datetime, time

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, Time, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DoctorSchedule(Base):
    """One weekly working block for a doctor. Times are IST. day_of_week: 0 = Monday ... 6 = Sunday."""

    __tablename__ = "doctor_schedules"
    __table_args__ = (
        # Block length must be a whole number of 20-minute (1200 s) slots.
        CheckConstraint(
            "MOD(EXTRACT(EPOCH FROM (end_time - start_time)), 1200) = 0",
            name="block_whole_slots",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("doctors.id", ondelete="RESTRICT"),
        index=True,
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )