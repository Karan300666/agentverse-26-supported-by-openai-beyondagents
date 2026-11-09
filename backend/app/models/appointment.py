import uuid
from datetime import date, datetime, time

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Time, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.doctor import Doctor

from app.db.base import Base


class Appointment(Base):
    """A booked slot. Date and time are IST. Rescheduling updates this same row."""

    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("status IN ('booked', 'cancelled', 'completed')", name="status_valid"),
        # One *booked* appointment per doctor per date and start time.
        # Cancelled/completed rows don't block the slot.
        Index(
            "uq_appointments_doctor_slot_booked",
            "doctor_id",
            "appointment_date",
            "start_time",
            unique=True,
            postgresql_where=text("status = 'booked'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT"),
        index=True,
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("doctors.id", ondelete="RESTRICT"),
        index=True,
    )
    appointment_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    status: Mapped[str] = mapped_column(String(20))
    fee_amount: Mapped[int]  # doctor's fee at booking time
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    doctor: Mapped[Doctor] = relationship(lazy="joined")