"""Booking accuracy set: the right appointment must land in the database, or none at all."""

from datetime import time

from evals.checks import judge, no_confirmation_sent
from evals.fixtures import (
    YES_EN,
    YES_HI,
    bilingual,
    booked,
    booked_specialty,
    count_appointments,
    nothing_booked,
    setup_other_booked,
)
from evals.checks import db

CATEGORY = "booking"


async def _no_ten_am(ctx) -> bool:
    return await count_appointments(ctx, doctor_name="Dr. Arjun Mehta", start=time(10), status="booked") == 0


SCENARIOS = [
    *bilingual(
        "explicit_date", CATEGORY,
        ["Please book Dr. Arjun Mehta on {day_text} at 10 am.", *YES_EN],
        ["Dr. Arjun Mehta ke saath {day_text} ko subah 10 baje appointment book kar do.", *YES_HI],
        [no_confirmation_sent(before_turn=1), booked("Dr. Arjun Mehta", "day", time(10))],
    ),
    *bilingual(
        "weekday_name", CATEGORY,
        ["Book Dr. Arjun Mehta this {day_weekday} at 11 am.", *YES_EN],
        ["Is {day_weekday} ko Dr. Arjun Mehta ke saath subah 11 baje book kar do.", *YES_HI],
        [no_confirmation_sent(before_turn=1), booked("Dr. Arjun Mehta", "day", time(11))],
    ),
    *bilingual(
        "spoken_time", CATEGORY,
        ["Book Dr. Arjun Mehta on {day_text} at twenty past ten in the morning.", *YES_EN],
        ["Dr. Arjun Mehta ke saath {day_text} ko subah das bajke bees minute pe book kar do.", *YES_HI],
        [no_confirmation_sent(before_turn=1), booked("Dr. Arjun Mehta", "day", time(10, 20))],
    ),
    *bilingual(
        "evening_time", CATEGORY,
        ["Book Dr. Kavita Nair on {day_text} at 4:40 in the evening.", *YES_EN],
        ["Dr. Kavita Nair ke saath {day_text} ko shaam 4:40 baje book kar do.", *YES_HI],
        [no_confirmation_sent(before_turn=1), booked("Dr. Kavita Nair", "day", time(16, 40))],
    ),
    *bilingual(
        "by_specialty", CATEGORY,
        ["Book a dermatologist for me on {day_text} at 9 am.", *YES_EN],
        ["{day_text} ko subah 9 baje kisi skin ke doctor ke saath book kar do.", *YES_HI],
        [no_confirmation_sent(before_turn=1), booked_specialty("Dermatology", "day", time(9))],
    ),
    *bilingual(
        "earliest_slot", CATEGORY,
        ["Book the earliest available slot with Dr. Vikram Singh on {day_text}.", *YES_EN],
        ["Dr. Vikram Singh ke saath {day_text} ko sabse pehla khaali slot book kar do.", *YES_HI],
        [no_confirmation_sent(before_turn=1), booked("Dr. Vikram Singh", "day", time(9))],
    ),
    *bilingual(
        "taken_then_alternative", CATEGORY,
        ["Book Dr. Arjun Mehta on {day_text} at 10 am.", "Okay, then book 10:20 instead.", *YES_EN],
        ["Dr. Arjun Mehta ke saath {day_text} ko subah 10 baje book kar do.", "Theek hai, toh 10:20 baje book kar do.", *YES_HI],
        [
            no_confirmation_sent(before_turn=2),
            booked("Dr. Arjun Mehta", "day", time(10, 20)),
            db("no 10:00 booking", _no_ten_am),
        ],
        setup=setup_other_booked("Dr. Arjun Mehta", time(10)),
    ),
    *bilingual(
        "doctor_not_working", CATEGORY,
        ["Book Dr. Arjun Mehta on {day_text} at 4 pm."],
        ["Dr. Arjun Mehta ke saath {day_text} ko shaam 4 baje book kar do."],
        [nothing_booked(), judge("Explains that Dr. Arjun Mehta is not available at 4 pm and offers times when he is available.")],
    ),
    *bilingual(
        "beyond_window", CATEGORY,
        ["Book Dr. Arjun Mehta on {far_text} at 10 am."],
        ["Dr. Arjun Mehta ke saath {far_text} ko subah 10 baje book kar do."],
        [nothing_booked(), judge("Explains that appointments can only be booked up to 7 days ahead.")],
    ),
    *bilingual(
        "past_date", CATEGORY,
        ["Book Dr. Arjun Mehta on {past_text} at 10 am."],
        ["Dr. Arjun Mehta ke saath {past_text} ko subah 10 baje book kar do."],
        [nothing_booked(), judge("Explains that it cannot book an appointment in the past.")],
    ),
]