import uuid
from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.services import doctor_service
from app.services.doctor_service import DateOutOfRangeError, DoctorNotFoundError
from tests.helpers import MONDAY, NOW, TUESDAY, add_schedule, make_appointment, make_doctor, make_patient, t


async def test_block_is_split_into_slots(db):
    doctor = await make_doctor(db)
    await add_schedule(db, doctor, 0, t(9), t(10))
    slots = await doctor_service.get_free_slots(db, doctor.id, MONDAY, now=NOW)
    assert slots == [t(9, 0), t(9, 20), t(9, 40)]


async def test_database_rejects_block_that_is_not_whole_slots(db):
    doctor = await make_doctor(db)
    with pytest.raises(IntegrityError):
        await add_schedule(db, doctor, 0, t(9, 0), t(9, 50))
    await db.rollback()


async def test_several_blocks_on_one_day(db):
    doctor = await make_doctor(db)
    await add_schedule(db, doctor, 0, t(9), t(9, 40))
    await add_schedule(db, doctor, 0, t(16), t(16, 40))
    slots = await doctor_service.get_free_slots(db, doctor.id, MONDAY, now=NOW)
    assert slots == [t(9, 0), t(9, 20), t(16, 0), t(16, 20)]


async def test_overlapping_blocks_do_not_duplicate_slots(db):
    doctor = await make_doctor(db)
    await add_schedule(db, doctor, 0, t(9), t(10))
    await add_schedule(db, doctor, 0, t(9, 20), t(10, 20))
    slots = await doctor_service.get_free_slots(db, doctor.id, MONDAY, now=NOW)
    assert slots == [t(9, 0), t(9, 20), t(9, 40), t(10, 0)]


async def test_booked_slot_is_excluded_but_cancelled_is_not(db):
    doctor = await make_doctor(db)
    patient = await make_patient(db)
    await add_schedule(db, doctor, 0, t(9), t(10))
    await make_appointment(db, patient, doctor, MONDAY, t(9, 20), "booked")
    await make_appointment(db, patient, doctor, MONDAY, t(9, 40), "cancelled")
    slots = await doctor_service.get_free_slots(db, doctor.id, MONDAY, now=NOW)
    assert slots == [t(9, 0), t(9, 40)]


async def test_past_slots_today_are_excluded(db):
    doctor = await make_doctor(db)
    await add_schedule(db, doctor, 0, t(9), t(10))
    now = NOW.replace(hour=9, minute=20)  # a slot starting exactly now is no longer bookable
    slots = await doctor_service.get_free_slots(db, doctor.id, MONDAY, now=now)
    assert slots == [t(9, 40)]


async def test_non_working_day_has_no_slots(db):
    doctor = await make_doctor(db)
    await add_schedule(db, doctor, 0, t(9), t(10))  # Mondays only
    assert await doctor_service.get_free_slots(db, doctor.id, TUESDAY, now=NOW) == []


async def test_booking_window_is_today_to_seven_days_ahead(db):
    doctor = await make_doctor(db)
    await add_schedule(db, doctor, 0, t(9), t(10))  # Mondays: 7 Jan and 14 Jan
    assert await doctor_service.get_free_slots(db, doctor.id, MONDAY + timedelta(days=7), now=NOW)
    with pytest.raises(DateOutOfRangeError):
        await doctor_service.get_free_slots(db, doctor.id, MONDAY + timedelta(days=8), now=NOW)
    with pytest.raises(DateOutOfRangeError):
        await doctor_service.get_free_slots(db, doctor.id, MONDAY - timedelta(days=1), now=NOW)


async def test_unknown_doctor(db):
    with pytest.raises(DoctorNotFoundError):
        await doctor_service.get_free_slots(db, uuid.uuid4(), MONDAY, now=NOW)