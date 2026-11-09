"""Booking, rescheduling, cancelling and history. All times are IST."""

import uuid
from datetime import date, datetime, time, timedelta

import logfire
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.services import doctor_service
from app.services.doctor_service import IST, get_free_slots, now_ist

STATUS_BOOKED = "booked"
STATUS_CANCELLED = "cancelled"
CHANGE_NOTICE = timedelta(hours=24)  # minimum notice to cancel or reschedule
SLOT_INDEX_NAME = "uq_appointments_doctor_slot_booked"


class SlotNotAvailableError(Exception):
    pass


class PatientBusyError(Exception):
    """The patient already has a booked appointment at that date and time."""


class DoctorAlreadyBookedError(Exception):
    """The patient already has a booked appointment with this doctor that day."""


class AppointmentNotFoundError(Exception):
    pass


class NotModifiableError(Exception):
    """Only booked appointments can be cancelled or rescheduled."""


class TooLateToChangeError(Exception):
    """Less than 24 hours before the appointment."""


class SlotUnchangedError(Exception):
    """Reschedule target equals the current date and time."""


def _start_datetime(appt: Appointment) -> datetime:
    return datetime.combine(appt.appointment_date, appt.start_time, tzinfo=IST)


def can_change(appt: Appointment, now: datetime | None = None) -> bool:
    """True if the appointment is booked and starts at least 24 hours from now."""
    now = now or now_ist()
    return appt.status == STATUS_BOOKED and _start_datetime(appt) - now >= CHANGE_NOTICE


async def _reload(db: AsyncSession, appointment_id: uuid.UUID) -> Appointment:
    result = await db.execute(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _get_own_appointment(
    db: AsyncSession, patient_id: uuid.UUID, appointment_id: uuid.UUID
) -> Appointment:
    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id, Appointment.patient_id == patient_id
        )
    )
    appt = result.scalar_one_or_none()
    if appt is None:
        raise AppointmentNotFoundError
    return appt


def _ensure_can_change(appt: Appointment, now: datetime) -> None:
    if appt.status != STATUS_BOOKED:
        raise NotModifiableError
    if _start_datetime(appt) - now < CHANGE_NOTICE:
        raise TooLateToChangeError


async def _ensure_patient_free(
    db: AsyncSession,
    patient_id: uuid.UUID,
    doctor_id: uuid.UUID,
    on_date: date,
    start: time,
    exclude_id: uuid.UUID | None = None,
) -> None:
    query = select(Appointment).where(
        Appointment.patient_id == patient_id,
        Appointment.appointment_date == on_date,
        Appointment.status == STATUS_BOOKED,
    )
    if exclude_id is not None:
        query = query.where(Appointment.id != exclude_id)
    existing = (await db.execute(query)).scalars().all()

    if any(a.start_time == start for a in existing):
        raise PatientBusyError
    if any(a.doctor_id == doctor_id for a in existing):
        raise DoctorAlreadyBookedError


async def _commit(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        # Someone else took the slot between our check and our write.
        if SLOT_INDEX_NAME in str(exc.orig):
            raise SlotNotAvailableError from None
        raise


# ---- Validation (no writes). Used for the "propose" step and re-run on execution. ----


async def validate_booking(
    db: AsyncSession,
    patient_id: uuid.UUID,
    doctor_id: uuid.UUID,
    on_date: date,
    start: time,
    *,
    now: datetime | None = None,
) -> Doctor:
    now = now or now_ist()
    free = await get_free_slots(db, doctor_id, on_date, now=now)
    if start not in free:
        raise SlotNotAvailableError
    await _ensure_patient_free(db, patient_id, doctor_id, on_date, start)
    return await doctor_service.get_doctor(db, doctor_id)


async def validate_cancel(
    db: AsyncSession,
    patient_id: uuid.UUID,
    appointment_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> Appointment:
    now = now or now_ist()
    appt = await _get_own_appointment(db, patient_id, appointment_id)
    _ensure_can_change(appt, now)
    return appt


async def validate_reschedule(
    db: AsyncSession,
    patient_id: uuid.UUID,
    appointment_id: uuid.UUID,
    new_date: date,
    new_start: time,
    *,
    now: datetime | None = None,
) -> Appointment:
    now = now or now_ist()
    appt = await _get_own_appointment(db, patient_id, appointment_id)
    _ensure_can_change(appt, now)  # the 24-hour rule applies to the current slot
    if (appt.appointment_date, appt.start_time) == (new_date, new_start):
        raise SlotUnchangedError

    free = await get_free_slots(db, appt.doctor_id, new_date, now=now)
    if new_start not in free:
        raise SlotNotAvailableError
    await _ensure_patient_free(
        db, patient_id, appt.doctor_id, new_date, new_start, exclude_id=appt.id
    )
    return appt


# ---- Actions (validate again, then write) ----


async def book_appointment(
    db: AsyncSession,
    patient_id: uuid.UUID,
    doctor_id: uuid.UUID,
    on_date: date,
    start: time,
    *,
    now: datetime | None = None,
) -> Appointment:
    with logfire.span("appointments.book", doctor_id=str(doctor_id), date=on_date.isoformat()):
        doctor = await validate_booking(db, patient_id, doctor_id, on_date, start, now=now)
        appt = Appointment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            appointment_date=on_date,
            start_time=start,
            status=STATUS_BOOKED,
            fee_amount=doctor.consultation_fee,
        )
        db.add(appt)
        await _commit(db)
        appt = await _reload(db, appt.id)
        logfire.info("appointment booked: id={id}", id=str(appt.id))
        return appt


async def cancel_appointment(
    db: AsyncSession,
    patient_id: uuid.UUID,
    appointment_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> Appointment:
    with logfire.span("appointments.cancel", appointment_id=str(appointment_id)):
        appt = await validate_cancel(db, patient_id, appointment_id, now=now)
        appt.status = STATUS_CANCELLED
        await _commit(db)
        appt = await _reload(db, appt.id)
        logfire.info("appointment cancelled: id={id}", id=str(appt.id))
        return appt


async def reschedule_appointment(
    db: AsyncSession,
    patient_id: uuid.UUID,
    appointment_id: uuid.UUID,
    new_date: date,
    new_start: time,
    *,
    now: datetime | None = None,
) -> Appointment:
    with logfire.span("appointments.reschedule", appointment_id=str(appointment_id)):
        appt = await validate_reschedule(
            db, patient_id, appointment_id, new_date, new_start, now=now
        )
        appt.appointment_date = new_date
        appt.start_time = new_start
        await _commit(db)
        appt = await _reload(db, appt.id)
        logfire.info("appointment rescheduled: id={id}", id=str(appt.id))
        return appt


async def list_history(db: AsyncSession, patient_id: uuid.UUID) -> list[Appointment]:
    """Every appointment of the patient, any status, newest (by appointment time) first."""
    result = await db.execute(
        select(Appointment)
        .where(Appointment.patient_id == patient_id)
        .order_by(Appointment.appointment_date.desc(), Appointment.start_time.desc())
    )
    appointments = list(result.scalars().all())
    logfire.info("history loaded: count={count}", count=len(appointments))
    return appointments