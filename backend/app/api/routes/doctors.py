import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.db.session import DbSession
from app.schemas.doctor import AvailabilityRead, DoctorRead, SpecialtyRead
from app.services import doctor_service
from app.services.doctor_service import DateOutOfRangeError, DoctorNotFoundError

router = APIRouter(tags=["doctors"])


@router.get("/specialties", response_model=list[SpecialtyRead])
async def list_specialties(db: DbSession):
    return await doctor_service.list_specialties(db)


@router.get("/doctors", response_model=list[DoctorRead])
async def search_doctors(db: DbSession, specialty: str | None = None, name: str | None = None):
    return await doctor_service.search_doctors(db, specialty=specialty, name=name)


@router.get("/doctors/{doctor_id}/availability", response_model=AvailabilityRead)
async def get_availability(
    doctor_id: uuid.UUID,
    on_date: Annotated[dt.date, Query(alias="date")],
    db: DbSession,
):
    try:
        slots = await doctor_service.get_free_slots(db, doctor_id, on_date)
    except DoctorNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Doctor not found") from None
    except DateOutOfRangeError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Date must be today or within the next {doctor_service.BOOKING_WINDOW_DAYS} days",
        ) from None

    return AvailabilityRead(
        doctor_id=doctor_id, 
        date=on_date,
        slot_minutes=await doctor_service.get_slot_minutes(db),
        slots=slots,
    )