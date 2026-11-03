from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient
from app.schemas.patient import PatientCreate


class PatientAlreadyExistsError(Exception):
    pass


class PatientNotFoundError(Exception):
    pass


async def get_by_phone(db: AsyncSession, phone: str) -> Patient | None:
    result = await db.execute(select(Patient).where(Patient.phone == phone))
    return result.scalar_one_or_none()


async def register_patient(db: AsyncSession, data: PatientCreate) -> Patient:
    if await get_by_phone(db, data.phone):
        raise PatientAlreadyExistsError

    patient = Patient(**data.model_dump())
    db.add(patient)
    try:
        await db.commit()
    except IntegrityError:  # two requests with the same phone at once
        await db.rollback()
        raise PatientAlreadyExistsError from None
    await db.refresh(patient)
    return patient


async def login_patient(db: AsyncSession, phone: str) -> Patient:
    patient = await get_by_phone(db, phone)
    if patient is None:
        raise PatientNotFoundError
    return patient