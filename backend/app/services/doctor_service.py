"""Doctor lookups and free-slot computation. All appointment times are IST."""

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import logfire
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.doctor_schedule import DoctorSchedule
from app.models.hospital_setting import HospitalSetting
from app.models.specialty import Specialty

IST = ZoneInfo("Asia/Kolkata")
BOOKING_WINDOW_DAYS = 7
SLOT_MINUTES_KEY = "appointment_slot_minutes"


class DoctorNotFoundError(Exception):
    pass


class DateOutOfRangeError(Exception):
    pass


class SettingsError(Exception):
    pass


def now_ist() -> datetime:
    return datetime.now(IST)


async def get_slot_minutes(db: AsyncSession) -> int:
    value = await db.scalar(
        select(HospitalSetting.value).where(HospitalSetting.key == SLOT_MINUTES_KEY)
    )
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        raise SettingsError(f"Setting '{SLOT_MINUTES_KEY}' is missing or not a number") from None
    if minutes <= 0:
        raise SettingsError(f"Setting '{SLOT_MINUTES_KEY}' must be positive")
    return minutes


async def list_specialties(db: AsyncSession) -> list[Specialty]:
    result = await db.execute(select(Specialty).order_by(Specialty.name))
    specialties = list(result.scalars().all())
    logfire.info("listed specialties: count={count}", count=len(specialties))
    return specialties


async def search_doctors(
    db: AsyncSession, *, specialty: str | None = None, name: str | None = None
) -> list[Doctor]:
    query = select(Doctor).join(Specialty, Doctor.specialty_id == Specialty.id)
    if specialty:
        query = query.where(func.lower(Specialty.name) == specialty.strip().lower())
    if name:
        query = query.where(Doctor.name.icontains(name.strip(), autoescape=True))
    result = await db.execute(query.order_by(Doctor.name))
    doctors = list(result.scalars().all())
    logfire.info(
        "doctor search: specialty={specialty} name={name} found={count}",
        specialty=specialty,
        name=name,
        count=len(doctors),
    )
    return doctors


async def get_doctor(db: AsyncSession, doctor_id: uuid.UUID) -> Doctor:
    doctor = await db.get(Doctor, doctor_id)
    if doctor is None:
        raise DoctorNotFoundError
    return doctor


def _block_slots(start: time, end: time, minutes: int) -> list[time]:
    """Split one working block into slot start times; a slot must fit fully inside the block."""
    step = timedelta(minutes=minutes)
    current = datetime.combine(date.min, start)
    limit = datetime.combine(date.min, end)
    slots: list[time] = []
    while current + step <= limit:
        slots.append(current.time())
        current += step
    return slots


async def get_free_slots(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    on_date: date,
    *,
    now: datetime | None = None,
) -> list[time]:
    """Free slot start times for a doctor on a date, sorted. Raises on bad date or doctor."""
    now = now or now_ist()
    today = now.date()
    if on_date < today or on_date > today + timedelta(days=BOOKING_WINDOW_DAYS):
        raise DateOutOfRangeError

    await get_doctor(db, doctor_id)
    minutes = await get_slot_minutes(db)

    blocks = (
        await db.execute(
            select(DoctorSchedule.start_time, DoctorSchedule.end_time).where(
                DoctorSchedule.doctor_id == doctor_id,
                DoctorSchedule.day_of_week == on_date.weekday(),  # 0 = Monday
            )
        )
    ).all()
    # A set, because overlapping blocks are allowed and must not create duplicate slots.
    all_slots = {slot for start, end in blocks for slot in _block_slots(start, end, minutes)}

    booked_result = await db.execute(
        select(Appointment.start_time).where(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == on_date,
            Appointment.status == "booked",
        )
    )
    free = all_slots - set(booked_result.scalars().all())

    if on_date == today:
        free = {slot for slot in free if slot > now.time()}  # only future slots today

    result = sorted(free)
    logfire.info(
        "free slots: doctor_id={doctor_id} date={date} count={count}",
        doctor_id=str(doctor_id),
        date=on_date.isoformat(),
        count=len(result),
    )
    return result