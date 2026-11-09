"""Appointment tools. Book, cancel and reschedule are two-step: propose, then confirm with a code."""

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from typing import Annotated, Any

from pydantic import Field, StringConstraints

from app.models.appointment import Appointment
from app.services import appointment_service as svc
from app.services.doctor_service import DateOutOfRangeError, DoctorNotFoundError, now_ist
from app.voice import confirmations
from app.voice.tools.base import Access, Tool, ToolArguments, ToolContext, ToolError, register
from app.voice.tools.general_tools import NoArguments

MAX_APPOINTMENTS = 50

NEXT_STEP = (
    "Nothing has been changed yet. Read these details to the patient and ask for a clear yes. "
    "Only after they confirm, call this same tool again with exactly the same arguments plus "
    "this confirmation_code. If they decline or want to change anything, do not use the code."
)

_ERRORS: dict[type[Exception], tuple[str, str]] = {
    svc.SlotNotAvailableError: (
        "slot_not_available",
        "That slot is not available. Check availability again and offer other slots.",
    ),
    svc.PatientBusyError: (
        "patient_busy",
        "The patient already has an appointment at that date and time.",
    ),
    svc.DoctorAlreadyBookedError: (
        "already_booked_with_doctor",
        "The patient already has an appointment with this doctor on that day.",
    ),
    svc.AppointmentNotFoundError: (
        "appointment_not_found",
        "No such appointment for this patient. Use get_my_appointments to see valid ids.",
    ),
    svc.NotModifiableError: (
        "not_modifiable",
        "Only booked appointments can be changed.",
    ),
    svc.TooLateToChangeError: (
        "too_late_to_change",
        "Appointments can only be changed at least 24 hours before they start.",
    ),
    svc.SlotUnchangedError: (
        "slot_unchanged",
        "The new date and time are the same as the current ones.",
    ),
    DoctorNotFoundError: (
        "doctor_not_found",
        "No doctor with that id. Use find_doctors to get a valid id.",
    ),
    DateOutOfRangeError: (
        "date_out_of_range",
        "Appointments can only be booked from today up to 7 days ahead.",
    ),
}

ConfirmationCode = Annotated[str, StringConstraints(min_length=1, max_length=64)]


class ConfirmableArguments(ToolArguments):
    confirmation_code: ConfirmationCode | None = Field(
        default=None,
        description=(
            "Leave empty on the first call. After the patient confirms, repeat the call with the "
            "confirmation_code returned by the first call."
        ),
    )


class BookArguments(ConfirmableArguments):
    doctor_id: uuid.UUID = Field(description="The doctor's id, from find_doctors.")
    appointment_date: dt.date = Field(description="Date as YYYY-MM-DD.")
    start_time: dt.time = Field(description="Slot start as HH:MM, taken from check_doctor_availability.")


class CancelArguments(ConfirmableArguments):
    appointment_id: uuid.UUID = Field(description="The appointment's id, from get_my_appointments.")


class RescheduleArguments(ConfirmableArguments):
    appointment_id: uuid.UUID = Field(description="The appointment's id, from get_my_appointments.")
    new_date: dt.date = Field(description="New date as YYYY-MM-DD.")
    new_start_time: dt.time = Field(description="New slot start as HH:MM, from check_doctor_availability.")


@contextmanager
def _translate_errors():
    try:
        yield
    except Exception as exc:
        mapped = _ERRORS.get(type(exc))
        if mapped is None:
            raise
        raise ToolError(*mapped) from None


def _when(day: dt.date, start: dt.time) -> dict[str, str]:
    return {"date": day.isoformat(), "weekday": day.strftime("%A"), "time": start.strftime("%H:%M")}


def _appointment_summary(appt: Appointment) -> dict[str, Any]:
    return {
        "id": str(appt.id),
        "doctor": appt.doctor.name,
        "specialty": appt.doctor.specialty.name,
        **_when(appt.appointment_date, appt.start_time),
        "status": appt.status,
        "fee_amount": appt.fee_amount,
        "currency": appt.doctor.currency,
    }


async def _two_step(
    ctx: ToolContext,
    tool_name: str,
    args: ConfirmableArguments,
    validate: Callable[[], Awaitable[dict[str, Any]]],
    execute: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    key = args.model_dump(mode="json", exclude={"confirmation_code"})

    if args.confirmation_code is None:
        with _translate_errors():
            summary = await validate()
        code = confirmations.create(ctx.session_id, ctx.patient.id, tool_name, key)
        return {
            "status": "confirmation_required",
            "confirmation_code": code,
            "summary": summary,
            "next_step": NEXT_STEP,
        }

    if not confirmations.consume(
        args.confirmation_code, ctx.session_id, ctx.patient.id, tool_name, key
    ):
        raise ToolError(
            "invalid_confirmation",
            "That confirmation is invalid, expired or does not match. Start again without a code.",
        )
    with _translate_errors():
        return await execute()


async def _get_my_appointments(ctx: ToolContext, args: NoArguments) -> dict[str, Any]:
    appointments = await svc.list_history(ctx.db, ctx.patient.id)
    now = now_ist()
    return {
        "count": len(appointments),
        "appointments": [
            {**_appointment_summary(a), "can_be_changed": svc.can_change(a, now)}
            for a in appointments[:MAX_APPOINTMENTS]
        ],
    }


async def _book_appointment(ctx: ToolContext, args: BookArguments) -> dict[str, Any]:
    async def validate() -> dict[str, Any]:
        doctor = await svc.validate_booking(
            ctx.db, ctx.patient.id, args.doctor_id, args.appointment_date, args.start_time
        )
        return {
            "doctor": doctor.name,
            "specialty": doctor.specialty.name,
            **_when(args.appointment_date, args.start_time),
            "fee_amount": doctor.consultation_fee,
            "currency": doctor.currency,
        }

    async def execute() -> dict[str, Any]:
        appt = await svc.book_appointment(
            ctx.db, ctx.patient.id, args.doctor_id, args.appointment_date, args.start_time
        )
        return {"status": "booked", "appointment": _appointment_summary(appt)}

    return await _two_step(ctx, "book_appointment", args, validate, execute)


async def _cancel_appointment(ctx: ToolContext, args: CancelArguments) -> dict[str, Any]:
    async def validate() -> dict[str, Any]:
        appt = await svc.validate_cancel(ctx.db, ctx.patient.id, args.appointment_id)
        return {"action": "cancel", **_appointment_summary(appt)}

    async def execute() -> dict[str, Any]:
        appt = await svc.cancel_appointment(ctx.db, ctx.patient.id, args.appointment_id)
        return {"status": "cancelled", "appointment": _appointment_summary(appt)}

    return await _two_step(ctx, "cancel_appointment", args, validate, execute)


async def _reschedule_appointment(ctx: ToolContext, args: RescheduleArguments) -> dict[str, Any]:
    async def validate() -> dict[str, Any]:
        appt = await svc.validate_reschedule(
            ctx.db, ctx.patient.id, args.appointment_id, args.new_date, args.new_start_time
        )
        return {
            "action": "reschedule",
            "doctor": appt.doctor.name,
            "from": _when(appt.appointment_date, appt.start_time),
            "to": _when(args.new_date, args.new_start_time),
        }

    async def execute() -> dict[str, Any]:
        appt = await svc.reschedule_appointment(
            ctx.db, ctx.patient.id, args.appointment_id, args.new_date, args.new_start_time
        )
        return {"status": "rescheduled", "appointment": _appointment_summary(appt)}

    return await _two_step(ctx, "reschedule_appointment", args, validate, execute)


register(
    Tool(
        name="get_my_appointments",
        description=(
            "List the calling patient's own appointments (any status, newest first). Use it to "
            "answer questions about their history and to get appointment ids for cancelling or "
            "rescheduling. 'can_be_changed' says whether cancel or reschedule is still allowed."
        ),
        access=Access.PATIENT,
        arguments=NoArguments,
        handler=_get_my_appointments,
    )
)

register(
    Tool(
        name="book_appointment",
        description=(
            "Book an appointment for the calling patient. TWO STEPS: the first call (no "
            "confirmation_code) books nothing and returns the details with a confirmation_code. "
            "Read the details to the patient; only after a clear yes, call again with identical "
            "arguments plus the code. Needs a doctor id from find_doctors and a start_time from "
            "check_doctor_availability."
        ),
        access=Access.WRITE,
        arguments=BookArguments,
        handler=_book_appointment,
    )
)

register(
    Tool(
        name="cancel_appointment",
        description=(
            "Cancel one of the calling patient's booked appointments. TWO STEPS: the first call "
            "(no confirmation_code) cancels nothing and returns the details with a "
            "confirmation_code. Only after the patient clearly says yes, call again with identical "
            "arguments plus the code. Needs an appointment id from get_my_appointments."
        ),
        access=Access.WRITE,
        arguments=CancelArguments,
        handler=_cancel_appointment,
    )
)

register(
    Tool(
        name="reschedule_appointment",
        description=(
            "Move one of the calling patient's booked appointments to a new date and time with "
            "the same doctor. TWO STEPS: the first call (no confirmation_code) changes nothing and "
            "returns the details with a confirmation_code. Only after the patient clearly says "
            "yes, call again with identical arguments plus the code. Needs an appointment id from "
            "get_my_appointments and a new slot from check_doctor_availability."
        ),
        access=Access.WRITE,
        arguments=RescheduleArguments,
        handler=_reschedule_appointment,
    )
)