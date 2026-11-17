"""Builders for test data, and fixed dates. Names and phones are unique per run so
they never clash with the real data in the database."""

import datetime as dt
import random
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.doctor_schedule import DoctorSchedule
from app.models.patient import Patient
from app.models.specialty import Specialty

IST = ZoneInfo("Asia/Kolkata")
RUN = uuid.uuid4().hex[:6]  # suffix that makes test names unique

# A fixed "now": Monday 7 January 2030, 08:00 IST.
NOW = dt.datetime(2030, 1, 7, 8, 0, tzinfo=IST)
MONDAY = NOW.date()
TUESDAY = MONDAY + dt.timedelta(days=1)
WEDNESDAY = MONDAY + dt.timedelta(days=2)
THURSDAY = MONDAY + dt.timedelta(days=3)
assert MONDAY.weekday() == 0


def t(hour: int, minute: int = 0) -> dt.time:
    return dt.time(hour, minute)


def _test_phone() -> str:
    # Real Indian mobile numbers never start with 1, so these can't clash with real patients.
    return f"1{random.randint(0, 999_999_999):09d}"


async def make_patient(db: AsyncSession, name: str = "Test Patient", age: int = 30) -> Patient:
    patient = Patient(name=f"{name} {RUN}", age=age, phone=_test_phone())
    db.add(patient)
    await db.commit()
    return patient


async def make_doctor(
    db: AsyncSession, name: str = "Dr. Test", specialty: str = "Cardiology", fee: int = 500
) -> Doctor:
    specialty_name = f"Test {specialty} {RUN}"
    existing = await db.execute(select(Specialty).where(Specialty.name == specialty_name))
    spec = existing.scalar_one_or_none()
    if spec is None:
        spec = Specialty(name=specialty_name)
        db.add(spec)
        await db.flush()
    doctor = Doctor(name=f"{name} {RUN}", specialty=spec, consultation_fee=fee, currency="INR")
    db.add(doctor)
    await db.commit()
    return doctor


async def add_schedule(
    db: AsyncSession, doctor: Doctor, day_of_week: int, start: dt.time, end: dt.time
) -> None:
    db.add(DoctorSchedule(doctor_id=doctor.id, day_of_week=day_of_week, start_time=start, end_time=end))
    await db.commit()


async def add_week(
    db: AsyncSession,
    doctor: Doctor,
    start: dt.time,
    end: dt.time,
    days: range = range(7),
) -> None:
    for day in days:
        db.add(DoctorSchedule(doctor_id=doctor.id, day_of_week=day, start_time=start, end_time=end))
    await db.commit()


async def make_appointment(
    db: AsyncSession,
    patient: Patient,
    doctor: Doctor,
    day: dt.date,
    start: dt.time,
    status: str = "booked",
) -> Appointment:
    appt = Appointment(
        patient_id=patient.id,
        doctor_id=doctor.id,
        doctor=doctor,
        appointment_date=day,
        start_time=start,
        status=status,
        fee_amount=doctor.consultation_fee,
    )
    db.add(appt)
    await db.commit()
    return appt