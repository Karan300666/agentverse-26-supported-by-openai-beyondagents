"""Shared helpers for the eval sets: database setup, database checks and bilingual scenarios."""

from collections.abc import Awaitable, Callable
from datetime import date, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.models.specialty import Specialty
from app.services.doctor_service import now_ist
from evals.checks import db, judge
from evals.harness import random_test_phone
from evals.models import Check, EvalContext, Scenario

Setup = Callable[[AsyncSession, Patient, dict[str, Any]], Awaitable[dict[str, Any]]]

HINDI_REPLY = (
    "Replies in Hindi (Latin or Devanagari script; English words such as doctor names, dates "
    "and times are fine), not in plain English."
)
YES_EN = ["Yes, please go ahead.", "Yes."]
YES_HI = ["Haan, kar do.", "Haan."]


# ---- database setup ----


async def get_doctor(session: AsyncSession, name: str) -> Doctor:
    doctor = await session.scalar(select(Doctor).where(Doctor.name == name))
    if doctor is None:
        raise RuntimeError(f"{name} not found. Load the demo doctors first.")
    return doctor


async def add_patient(session: AsyncSession, name: str) -> Patient:
    patient = Patient(name=name, age=40, phone=random_test_phone())
    session.add(patient)
    await session.commit()
    return patient


async def add_appointment(
    session: AsyncSession, patient: Patient, doctor_name: str, day: date, start: time, status: str = "booked"
) -> None:
    doctor = await get_doctor(session, doctor_name)
    session.add(
        Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            appointment_date=day,
            start_time=start,
            status=status,
            fee_amount=doctor.consultation_fee,
        )
    )
    await session.commit()


async def add_doctor(session: AsyncSession, name: str, specialty: str, fee: int = 500) -> Doctor:
    spec = await session.scalar(select(Specialty).where(Specialty.name == specialty))
    if spec is None:
        spec = Specialty(name=specialty)
        session.add(spec)
        await session.flush()
    doctor = Doctor(name=name, specialty=spec, consultation_fee=fee, currency="INR")
    session.add(doctor)
    await session.commit()
    return doctor


async def setup_history(session, patient, data) -> dict[str, Any]:
    today = data["today"]
    await add_appointment(session, patient, "Dr. Arjun Mehta", today - timedelta(days=10), time(10), "completed")
    await add_appointment(session, patient, "Dr. Priya Sharma", today - timedelta(days=20), time(9, 20), "completed")
    return {}


def setup_booked(doctor_name: str, start: time) -> Setup:
    """The eval patient already has a booking on `day`."""

    async def setup(session, patient, data):
        await add_appointment(session, patient, doctor_name, data["day"], start)
        return {}

    return setup


def setup_other_booked(doctor_name: str, start: time) -> Setup:
    """Another patient already holds this slot on `day`."""

    async def setup(session, patient, data):
        other = await add_patient(session, "Other Eval Patient")
        await add_appointment(session, other, doctor_name, data["day"], start)
        return {}

    return setup


async def setup_soon(session, patient, data) -> dict[str, Any]:
    """A booking about 3 hours from now, so the 24-hour rule blocks changes."""
    soon = now_ist() + timedelta(hours=3)
    soon = soon.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=(soon.minute // 20 + 1) * 20)
    await add_appointment(session, patient, "Dr. Arjun Mehta", soon.date(), soon.time())
    return {"soon_date": soon.date(), "soon_time": soon.time()}


# ---- database checks ----


async def count_appointments(
    ctx: EvalContext,
    *,
    patient_id=None,
    doctor_name: str | None = None,
    specialty: str | None = None,
    day: date | None = None,
    start: time | None = None,
    status: str | None = None,
) -> int:
    query = (
        select(func.count())
        .select_from(Appointment)
        .where(Appointment.patient_id == (patient_id or ctx.patient.id))
    )
    if doctor_name:
        doctor = await get_doctor(ctx.db, doctor_name)
        query = query.where(Appointment.doctor_id == doctor.id)
    if specialty:
        query = (
            query.join(Doctor, Doctor.id == Appointment.doctor_id)
            .join(Specialty, Specialty.id == Doctor.specialty_id)
            .where(Specialty.name == specialty)
        )
    if day is not None:
        query = query.where(Appointment.appointment_date == day)
    if start is not None:
        query = query.where(Appointment.start_time == start)
    if status:
        query = query.where(Appointment.status == status)
    return await ctx.db.scalar(query)


def _value(ctx: EvalContext, value):
    """A literal value, or a key into the scenario data."""
    return ctx.data[value] if isinstance(value, str) else value


def booked(doctor_name: str, day_key: str, start: time | str) -> Check:
    async def condition(ctx):
        n = await count_appointments(
            ctx, doctor_name=doctor_name, day=ctx.data[day_key], start=_value(ctx, start), status="booked"
        )
        return n == 1

    return db(f"{doctor_name} booked ({day_key})", condition)


def booked_specialty(specialty: str, day_key: str, start: time) -> Check:
    async def condition(ctx):
        n = await count_appointments(ctx, specialty=specialty, day=ctx.data[day_key], start=start, status="booked")
        return n == 1

    return db(f"{specialty} booked at {start:%H:%M}", condition)


def has_status(doctor_name: str, day_key: str, start: time | str, status: str) -> Check:
    async def condition(ctx):
        n = await count_appointments(
            ctx, doctor_name=doctor_name, day=ctx.data[day_key], start=_value(ctx, start), status=status
        )
        return n == 1

    return db(f"{doctor_name} appointment is {status}", condition)


def nothing_booked() -> Check:
    async def condition(ctx):
        return await count_appointments(ctx, status="booked") == 0

    return db("nothing booked", condition)


# ---- scenario builder ----


def bilingual(
    base_id: str,
    category: str,
    en: list[str],
    hi: list[str],
    checks: list[Check],
    *,
    setup: Setup | None = None,
    hindi_check: bool = False,
) -> list[Scenario]:
    """The same case in English and Hinglish."""
    hi_checks = [*checks, judge(HINDI_REPLY)] if hindi_check else list(checks)
    return [
        Scenario(f"{base_id}_en", category, en, list(checks), setup),
        Scenario(f"{base_id}_hi", category, hi, hi_checks, setup),
    ]