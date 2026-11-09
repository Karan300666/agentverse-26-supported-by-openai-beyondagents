"""Identifies the calling patient from the X-Patient-Phone header (demo auth, no tokens)."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.db.session import DbSession
from app.models.patient import Patient
from app.services import patient_service


async def get_current_patient(
    db: DbSession,
    x_patient_phone: Annotated[str, Header(pattern=r"^[0-9]{10}$")],
) -> Patient:
    patient = await patient_service.get_by_phone(db, x_patient_phone)
    if patient is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Unknown patient")
    return patient


CurrentPatient = Annotated[Patient, Depends(get_current_patient)]