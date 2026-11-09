"""Read-only doctor tools: public hospital information, no patient data."""

import datetime as dt
import uuid
from typing import Annotated, Any

from pydantic import Field, StringConstraints

from app.models.doctor import Doctor
from app.services import doctor_service
from app.services.doctor_service import (
    BOOKING_WINDOW_DAYS,
    DateOutOfRangeError,
    DoctorNotFoundError,
)
from app.voice.tools.base import Access, Tool, ToolArguments, ToolContext, ToolError, register

MAX_DOCTORS = 20

SearchText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class NoArguments(ToolArguments):
    pass


class FindDoctorsArguments(ToolArguments):
    specialty: SearchText | None = Field(
        default=None,
        description="Exact specialty name as returned by list_specialties, in English.",
    )
    name: SearchText | None = Field(
        default=None,
        description="Part of the doctor's name, written in English letters.",
    )


class CheckAvailabilityArguments(ToolArguments):
    doctor_id: uuid.UUID = Field(description="The doctor's id, taken from find_doctors.")
    appointment_date: dt.date = Field(description="The date to check, as YYYY-MM-DD.")


def _doctor_summary(doctor: Doctor) -> dict[str, Any]:
    return {
        "id": str(doctor.id),
        "name": doctor.name,
        "specialty": doctor.specialty.name,
        "consultation_fee": doctor.consultation_fee,
        "currency": doctor.currency,
    }


async def _list_specialties(ctx: ToolContext, args: NoArguments) -> dict[str, Any]:
    specialties = await doctor_service.list_specialties(ctx.db)
    return {"specialties": [s.name for s in specialties]}


async def _find_doctors(ctx: ToolContext, args: FindDoctorsArguments) -> dict[str, Any]:
    doctors = await doctor_service.search_doctors(ctx.db, specialty=args.specialty, name=args.name)

    if not doctors and args.specialty:
        known = [s.name for s in await doctor_service.list_specialties(ctx.db)]
        if args.specialty.lower() not in {k.lower() for k in known}:
            raise ToolError(
                "unknown_specialty",
                "No such specialty. Available specialties: " + ", ".join(known),
            )

    return {
        "count": len(doctors),
        "doctors": [_doctor_summary(d) for d in doctors[:MAX_DOCTORS]],
    }


async def _check_doctor_availability(
    ctx: ToolContext, args: CheckAvailabilityArguments
) -> dict[str, Any]:
    try:
        slots = await doctor_service.get_free_slots(ctx.db, args.doctor_id, args.appointment_date)
    except DoctorNotFoundError:
        raise ToolError(
            "doctor_not_found", "No doctor with that id. Use find_doctors to get a valid id."
        ) from None
    except DateOutOfRangeError:
        raise ToolError(
            "date_out_of_range",
            f"Appointments can only be booked from today up to {BOOKING_WINDOW_DAYS} days ahead.",
        ) from None

    doctor = await doctor_service.get_doctor(ctx.db, args.doctor_id)
    return {
        "doctor": {"id": str(doctor.id), "name": doctor.name, "specialty": doctor.specialty.name},
        "date": args.appointment_date.isoformat(),
        "slot_minutes": await doctor_service.get_slot_minutes(ctx.db),
        "free_slots": [slot.strftime("%H:%M") for slot in slots],
        "count": len(slots),
    }


register(
    Tool(
        name="list_specialties",
        description=(
            "List the medical specialties the hospital offers. Use it to map what the patient "
            "needs (for example heart problems) to an exact specialty name."
        ),
        access=Access.PUBLIC,
        arguments=NoArguments,
        handler=_list_specialties,
    )
)

register(
    Tool(
        name="find_doctors",
        description=(
            "Find doctors by exact specialty name (from list_specialties) and/or part of the "
            "doctor's name in English letters. Returns each doctor's id, name, specialty and fee. "
            "The doctor id is needed by other tools."
        ),
        access=Access.PUBLIC,
        arguments=FindDoctorsArguments,
        handler=_find_doctors,
    )
)

register(
    Tool(
        name="check_doctor_availability",
        description=(
            "List one doctor's free appointment slots on a single date (hospital time, 24-hour "
            "HH:MM). Needs a doctor id from find_doctors. Dates run from today up to 7 days ahead."
        ),
        access=Access.PUBLIC,
        arguments=CheckAvailabilityArguments,
        handler=_check_doctor_availability,
    )
)