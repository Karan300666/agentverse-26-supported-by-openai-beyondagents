import datetime as dt
import json
import uuid
from types import SimpleNamespace

import pytest_asyncio
from sqlalchemy import func, select

from app.models.appointment import Appointment
from app.services import doctor_service
from app.voice.tool_executor import execute_tool
from app.voice.tools import Access, Tool, ToolContext
from app.voice.tools import base as tools_base
from app.voice.tools.general_tools import NoArguments
from tests.helpers import add_week, make_appointment, make_doctor, make_patient, t

# The tool handlers use the real clock, so these tests use a real date 3 days ahead.
DAY = doctor_service.now_ist().date() + dt.timedelta(days=3)


@pytest_asyncio.fixture
async def world(db):
    doctor = await make_doctor(db, name="Dr. Tool", specialty="Cardiology", fee=800)
    await add_week(db, doctor, t(9), t(13))  # every day, 12 slots
    return SimpleNamespace(doctor=doctor, p1=await make_patient(db), p2=await make_patient(db))


def ctx(db, patient, session_id=None):
    return ToolContext(db=db, patient=patient, session_id=session_id or uuid.uuid4())


async def call(context, tool_name, **arguments):
    return await execute_tool(context, tool_name, json.dumps(arguments))


async def appointment_count(db, patient, status=None):
    """Counts only this patient's appointments, so real data in the table doesn't matter."""
    query = select(func.count()).select_from(Appointment).where(Appointment.patient_id == patient.id)
    if status:
        query = query.where(Appointment.status == status)
    return await db.scalar(query)


def book_args(world, start="10:00"):
    return dict(
        doctor_id=str(world.doctor.id), appointment_date=DAY.isoformat(), start_time=start
    )


# ---- argument validation ----


async def test_unknown_tool(db, world):
    result = await call(ctx(db, world.p1), "drop_all_tables")
    assert not result["ok"] and result["error"]["code"] == "unknown_tool"


async def test_arguments_must_be_json(db, world):
    result = await execute_tool(ctx(db, world.p1), "find_doctors", "not json")
    assert result["error"]["code"] == "invalid_arguments"


async def test_arguments_must_be_an_object(db, world):
    result = await execute_tool(ctx(db, world.p1), "find_doctors", "[1, 2]")
    assert result["error"]["code"] == "invalid_arguments"


async def test_model_cannot_supply_a_patient_id(db, world):
    result = await call(ctx(db, world.p1), "get_my_appointments", patient_id=str(world.p2.id))
    assert result["error"]["code"] == "invalid_arguments"


async def test_missing_required_argument(db, world):
    result = await call(ctx(db, world.p1), "check_doctor_availability", appointment_date=DAY.isoformat())
    assert result["error"]["code"] == "invalid_arguments"


async def test_malformed_uuid(db, world):
    result = await call(
        ctx(db, world.p1), "check_doctor_availability", doctor_id="abc", appointment_date=DAY.isoformat()
    )
    assert result["error"]["code"] == "invalid_arguments"


async def test_crashing_tool_returns_a_generic_error(db, world, monkeypatch):
    async def handler(context, args):
        raise RuntimeError("secret detail")

    boom = Tool(name="boom", description="x", access=Access.PUBLIC, arguments=NoArguments, handler=handler)
    monkeypatch.setitem(tools_base._TOOLS, "boom", boom)
    result = await call(ctx(db, world.p1), "boom")
    assert result["error"]["code"] == "internal_error"
    assert "secret" not in result["error"]["message"]


# ---- read-only tools ----


async def test_find_doctors_by_specialty_and_name(db, world):
    by_specialty = await call(ctx(db, world.p1), "find_doctors", specialty=world.doctor.specialty.name)
    assert by_specialty["data"]["count"] == 1
    by_name = await call(ctx(db, world.p1), "find_doctors", name=world.doctor.name)
    assert by_name["data"]["doctors"][0]["id"] == str(world.doctor.id)


async def test_unknown_specialty_lists_valid_ones(db, world):
    result = await call(ctx(db, world.p1), "find_doctors", specialty="no such specialty")
    assert result["error"]["code"] == "unknown_specialty"
    assert world.doctor.specialty.name in result["error"]["message"]


async def test_check_availability(db, world):
    result = await call(
        ctx(db, world.p1),
        "check_doctor_availability",
        doctor_id=str(world.doctor.id),
        appointment_date=DAY.isoformat(),
    )
    assert result["data"]["count"] == 12
    assert result["data"]["free_slots"][0] == "09:00"


async def test_availability_outside_window(db, world):
    far = (DAY + dt.timedelta(days=30)).isoformat()
    result = await call(
        ctx(db, world.p1), "check_doctor_availability", doctor_id=str(world.doctor.id), appointment_date=far
    )
    assert result["error"]["code"] == "date_out_of_range"


# ---- two-step confirmation ----


async def test_proposing_books_nothing_and_confirming_books(db, world):
    c = ctx(db, world.p1)
    proposal = await call(c, "book_appointment", **book_args(world))
    assert proposal["data"]["status"] == "confirmation_required"
    assert await appointment_count(db, world.p1) == 0

    code = proposal["data"]["confirmation_code"]
    done = await call(c, "book_appointment", **book_args(world), confirmation_code=code)
    assert done["data"]["status"] == "booked"
    assert await appointment_count(db, world.p1, "booked") == 1


async def test_a_code_works_only_once(db, world):
    c = ctx(db, world.p1)
    code = (await call(c, "book_appointment", **book_args(world)))["data"]["confirmation_code"]
    await call(c, "book_appointment", **book_args(world), confirmation_code=code)
    again = await call(c, "book_appointment", **book_args(world), confirmation_code=code)
    assert again["error"]["code"] == "invalid_confirmation"
    assert await appointment_count(db, world.p1) == 1


async def test_changing_arguments_invalidates_the_code(db, world):
    c = ctx(db, world.p1)
    code = (await call(c, "book_appointment", **book_args(world)))["data"]["confirmation_code"]
    changed = await call(c, "book_appointment", **book_args(world, "10:20"), confirmation_code=code)
    assert changed["error"]["code"] == "invalid_confirmation"
    original = await call(c, "book_appointment", **book_args(world), confirmation_code=code)
    assert original["error"]["code"] == "invalid_confirmation"  # the code was spent
    assert await appointment_count(db, world.p1) == 0


async def test_code_from_another_session_is_rejected(db, world):
    code = (await call(ctx(db, world.p1), "book_appointment", **book_args(world)))["data"]["confirmation_code"]
    other_session = ctx(db, world.p1)
    result = await call(other_session, "book_appointment", **book_args(world), confirmation_code=code)
    assert result["error"]["code"] == "invalid_confirmation"
    assert await appointment_count(db, world.p1) == 0


async def test_code_from_another_patient_is_rejected(db, world):
    session_id = uuid.uuid4()
    code = (await call(ctx(db, world.p1, session_id), "book_appointment", **book_args(world)))["data"][
        "confirmation_code"
    ]
    result = await call(ctx(db, world.p2, session_id), "book_appointment", **book_args(world), confirmation_code=code)
    assert result["error"]["code"] == "invalid_confirmation"
    assert await appointment_count(db, world.p1) == 0
    assert await appointment_count(db, world.p2) == 0


async def test_made_up_code_is_rejected(db, world):
    result = await call(ctx(db, world.p1), "book_appointment", **book_args(world), confirmation_code="nope")
    assert result["error"]["code"] == "invalid_confirmation"


async def test_code_expires(db, world, clock):
    c = ctx(db, world.p1)
    code = (await call(c, "book_appointment", **book_args(world)))["data"]["confirmation_code"]
    clock.advance(301)  # the code lives 5 minutes
    result = await call(c, "book_appointment", **book_args(world), confirmation_code=code)
    assert result["error"]["code"] == "invalid_confirmation"
    assert await appointment_count(db, world.p1) == 0


# ---- ownership ----


async def test_my_appointments_shows_only_own(db, world):
    await make_appointment(db, world.p1, world.doctor, DAY, t(9))
    await make_appointment(db, world.p2, world.doctor, DAY, t(10))
    result = await call(ctx(db, world.p1), "get_my_appointments")
    assert result["data"]["count"] == 1


async def test_cannot_cancel_someone_elses_appointment(db, world):
    appt = await make_appointment(db, world.p1, world.doctor, DAY, t(9))
    result = await call(ctx(db, world.p2), "cancel_appointment", appointment_id=str(appt.id))
    assert result["error"]["code"] == "appointment_not_found"


async def test_cancel_is_two_steps(db, world):
    appt = await make_appointment(db, world.p1, world.doctor, DAY, t(9))
    c = ctx(db, world.p1)
    proposal = await call(c, "cancel_appointment", appointment_id=str(appt.id))
    assert proposal["data"]["status"] == "confirmation_required"
    assert await appointment_count(db, world.p1, "booked") == 1

    code = proposal["data"]["confirmation_code"]
    done = await call(c, "cancel_appointment", appointment_id=str(appt.id), confirmation_code=code)
    assert done["data"]["status"] == "cancelled"
    assert await appointment_count(db, world.p1, "booked") == 0