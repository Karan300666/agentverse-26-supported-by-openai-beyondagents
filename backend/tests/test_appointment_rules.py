from datetime import timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError

from app.services import appointment_service as svc
from app.services.doctor_service import DateOutOfRangeError
from tests.helpers import (
    MONDAY,
    NOW,
    THURSDAY,
    TUESDAY,
    WEDNESDAY,
    add_week,
    make_appointment,
    make_doctor,
    make_patient,
    t,
)


@pytest_asyncio.fixture
async def world(db):
    a = await make_doctor(db, name="Dr. A", specialty="Cardiology", fee=700)
    b = await make_doctor(db, name="Dr. B", specialty="Dermatology", fee=400)
    for doctor in (a, b):
        await add_week(db, doctor, t(9), t(13), days=range(5))  # Mon-Fri
    return SimpleNamespace(
        a=a, b=b, p1=await make_patient(db), p2=await make_patient(db)
    )


async def book(db, patient, doctor, day, start, now=NOW):
    return await svc.book_appointment(db, patient.id, doctor.id, day, start, now=now)


# ---- booking ----


async def test_booking_snapshots_the_fee(db, world):
    appt = await book(db, world.p1, world.a, WEDNESDAY, t(9))
    assert appt.status == "booked"
    assert appt.fee_amount == 700


async def test_two_patients_cannot_take_the_same_slot(db, world):
    await book(db, world.p1, world.a, WEDNESDAY, t(9))
    with pytest.raises(svc.SlotNotAvailableError):
        await book(db, world.p2, world.a, WEDNESDAY, t(9))


async def test_patient_cannot_book_two_doctors_at_the_same_time(db, world):
    await book(db, world.p1, world.a, WEDNESDAY, t(9))
    with pytest.raises(svc.PatientBusyError):
        await book(db, world.p1, world.b, WEDNESDAY, t(9))


async def test_patient_cannot_book_the_same_doctor_twice_in_a_day(db, world):
    await book(db, world.p1, world.a, WEDNESDAY, t(9))
    with pytest.raises(svc.DoctorAlreadyBookedError):
        await book(db, world.p1, world.a, WEDNESDAY, t(10))


async def test_same_doctor_on_different_days_is_fine(db, world):
    await book(db, world.p1, world.a, WEDNESDAY, t(9))
    await book(db, world.p1, world.a, THURSDAY, t(9))


async def test_cancelled_slot_can_be_booked_again(db, world):
    appt = await book(db, world.p1, world.a, WEDNESDAY, t(9))
    await svc.cancel_appointment(db, world.p1.id, appt.id, now=NOW)
    await book(db, world.p2, world.a, WEDNESDAY, t(9))


async def test_cannot_book_outside_the_window(db, world):
    with pytest.raises(DateOutOfRangeError):
        await book(db, world.p1, world.a, MONDAY + timedelta(days=8), t(9))


async def test_cannot_book_a_time_that_has_passed(db, world):
    with pytest.raises(svc.SlotNotAvailableError):
        await book(db, world.p1, world.a, MONDAY, t(9), now=NOW.replace(hour=10))


async def test_database_blocks_two_booked_rows_for_one_slot(db, world):
    await make_appointment(db, world.p1, world.a, WEDNESDAY, t(9), "booked")
    with pytest.raises(IntegrityError):
        await make_appointment(db, world.p2, world.a, WEDNESDAY, t(9), "booked")
    await db.rollback()


async def test_database_allows_cancelled_rows_for_a_booked_slot(db, world):
    await make_appointment(db, world.p1, world.a, WEDNESDAY, t(9), "booked")
    await make_appointment(db, world.p2, world.a, WEDNESDAY, t(9), "cancelled")


# ---- 24-hour notice ----


async def test_cancel_with_enough_notice(db, world):
    appt = await book(db, world.p1, world.a, TUESDAY, t(9))
    cancelled = await svc.cancel_appointment(db, world.p1.id, appt.id, now=NOW)  # 25 hours before
    assert cancelled.status == "cancelled"


async def test_cancel_exactly_24_hours_before_is_allowed(db, world):
    appt = await book(db, world.p1, world.a, TUESDAY, t(9))
    cancelled = await svc.cancel_appointment(db, world.p1.id, appt.id, now=NOW.replace(hour=9))
    assert cancelled.status == "cancelled"


async def test_cancel_less_than_24_hours_before_is_refused(db, world):
    appt = await book(db, world.p1, world.a, TUESDAY, t(9))
    with pytest.raises(svc.TooLateToChangeError):
        await svc.cancel_appointment(db, world.p1.id, appt.id, now=NOW.replace(hour=10))  # 23 hours


async def test_cannot_cancel_twice(db, world):
    appt = await book(db, world.p1, world.a, WEDNESDAY, t(9))
    await svc.cancel_appointment(db, world.p1.id, appt.id, now=NOW)
    with pytest.raises(svc.NotModifiableError):
        await svc.cancel_appointment(db, world.p1.id, appt.id, now=NOW)


# ---- reschedule ----


async def test_reschedule_moves_the_same_row(db, world):
    appt = await book(db, world.p1, world.a, WEDNESDAY, t(9))
    moved = await svc.reschedule_appointment(db, world.p1.id, appt.id, THURSDAY, t(10), now=NOW)
    assert moved.id == appt.id
    assert (moved.appointment_date, moved.start_time) == (THURSDAY, t(10))
    assert moved.doctor_id == world.a.id
    assert moved.fee_amount == 700


async def test_reschedule_into_a_taken_slot_is_refused(db, world):
    await book(db, world.p2, world.a, THURSDAY, t(10))
    appt = await book(db, world.p1, world.a, WEDNESDAY, t(9))
    with pytest.raises(svc.SlotNotAvailableError):
        await svc.reschedule_appointment(db, world.p1.id, appt.id, THURSDAY, t(10), now=NOW)


async def test_reschedule_to_the_same_slot_is_refused(db, world):
    appt = await book(db, world.p1, world.a, WEDNESDAY, t(9))
    with pytest.raises(svc.SlotUnchangedError):
        await svc.reschedule_appointment(db, world.p1.id, appt.id, WEDNESDAY, t(9), now=NOW)


async def test_reschedule_less_than_24_hours_before_is_refused(db, world):
    appt = await book(db, world.p1, world.a, TUESDAY, t(9))
    with pytest.raises(svc.TooLateToChangeError):
        await svc.reschedule_appointment(
            db, world.p1.id, appt.id, THURSDAY, t(10), now=NOW.replace(hour=10)
        )


async def test_reschedule_cannot_clash_with_patients_other_appointment(db, world):
    await book(db, world.p1, world.b, THURSDAY, t(10))
    appt = await book(db, world.p1, world.a, WEDNESDAY, t(9))
    with pytest.raises(svc.PatientBusyError):
        await svc.reschedule_appointment(db, world.p1.id, appt.id, THURSDAY, t(10), now=NOW)


# ---- ownership and history ----


async def test_patient_cannot_change_someone_elses_appointment(db, world):
    appt = await book(db, world.p1, world.a, WEDNESDAY, t(9))
    with pytest.raises(svc.AppointmentNotFoundError):
        await svc.cancel_appointment(db, world.p2.id, appt.id, now=NOW)
    with pytest.raises(svc.AppointmentNotFoundError):
        await svc.reschedule_appointment(db, world.p2.id, appt.id, THURSDAY, t(10), now=NOW)


async def test_history_is_own_only_and_newest_first(db, world):
    await book(db, world.p1, world.a, WEDNESDAY, t(9))
    await book(db, world.p1, world.a, THURSDAY, t(9))
    await book(db, world.p2, world.b, WEDNESDAY, t(10))
    history = await svc.list_history(db, world.p1.id)
    assert [a.appointment_date for a in history] == [THURSDAY, WEDNESDAY]
    assert all(a.patient_id == world.p1.id for a in history)