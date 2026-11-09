import uuid

from fastapi import APIRouter, HTTPException, status

from app.core.security import CurrentPatient
from app.db.session import DbSession
from app.schemas.appointment import AppointmentBook, AppointmentRead, AppointmentReschedule
from app.services import appointment_service as svc
from app.services.doctor_service import DateOutOfRangeError, DoctorNotFoundError

router = APIRouter(prefix="/appointments", tags=["appointments"])

# Service error -> (HTTP status, message)
_ERRORS: list[tuple[type[Exception], int, str]] = [
    (svc.SlotNotAvailableError, 409, "That slot is not available."),
    (svc.PatientBusyError, 409, "You already have an appointment at that date and time."),
    (svc.DoctorAlreadyBookedError, 409, "You already have an appointment with this doctor that day."),
    (svc.NotModifiableError, 409, "Only booked appointments can be changed."),
    (svc.TooLateToChangeError, 409, "Appointments can only be changed at least 24 hours before they start."),
    (svc.AppointmentNotFoundError, 404, "Appointment not found."),
    (DoctorNotFoundError, 404, "Doctor not found."),
    (DateOutOfRangeError, 400, "Date must be today or within the next 7 days."),
    (svc.SlotUnchangedError, 400, "The new date and time are the same as the current ones."),
]


def _to_http(exc: Exception) -> HTTPException | None:
    for cls, code, detail in _ERRORS:
        if isinstance(exc, cls):
            return HTTPException(code, detail=detail)
    return None


@router.get("", response_model=list[AppointmentRead])
async def history(patient: CurrentPatient, db: DbSession):
    return await svc.list_history(db, patient.id)


@router.post("", response_model=AppointmentRead, status_code=status.HTTP_201_CREATED)
async def book(data: AppointmentBook, patient: CurrentPatient, db: DbSession):
    try:
        return await svc.book_appointment(
            db, patient.id, data.doctor_id, data.appointment_date, data.start_time
        )
    except Exception as exc:
        http_exc = _to_http(exc)
        if http_exc is None:
            raise
        raise http_exc from None


@router.post("/{appointment_id}/cancel", response_model=AppointmentRead)
async def cancel(appointment_id: uuid.UUID, patient: CurrentPatient, db: DbSession):
    try:
        return await svc.cancel_appointment(db, patient.id, appointment_id)
    except Exception as exc:
        http_exc = _to_http(exc)
        if http_exc is None:
            raise
        raise http_exc from None


@router.post("/{appointment_id}/reschedule", response_model=AppointmentRead)
async def reschedule(
    appointment_id: uuid.UUID,
    data: AppointmentReschedule,
    patient: CurrentPatient,
    db: DbSession,
):
    try:
        return await svc.reschedule_appointment(
            db, patient.id, appointment_id, data.appointment_date, data.start_time
        )
    except Exception as exc:
        http_exc = _to_http(exc)
        if http_exc is None:
            raise
        raise http_exc from None