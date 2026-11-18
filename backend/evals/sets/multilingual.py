"""Multilingual set: full tasks in Hinglish, plus switching language mid-call."""

from datetime import time

from evals.checks import called, called_with, judge, no_confirmation_sent, reply_contains
from evals.fixtures import (
    HINDI_REPLY,
    YES_HI,
    booked,
    has_status,
    setup_booked,
    setup_history,
    setup_soon,
)
from evals.models import Scenario

CATEGORY = "multilingual"
HI = judge(HINDI_REPLY)

SCENARIOS = [
    # ---- tasks in Hinglish ----
    Scenario("hi_specialties", CATEGORY, ["Aapke hospital mein kaun kaun si specialties hain?"],
             [called("list_specialties"), HI]),
    Scenario("hi_heart_doctor", CATEGORY, ["Mujhe dil ka doctor chahiye."],
             [called_with("find_doctors", lambda a, d: (a.get("specialty") or "").lower() == "cardiology", "with Cardiology"), HI]),
    Scenario("hi_availability", CATEGORY, ["Kya Dr. Arjun Mehta {day_text} ko free hain?"],
             [called_with("check_doctor_availability", lambda a, d: a.get("appointment_date") == d["day"].isoformat(), "for the asked date"), HI]),
    Scenario("hi_tomorrow", CATEGORY, ["Kya Dr. Kavita Nair kal available hain?"],
             [called("get_current_datetime"),
              called_with("check_doctor_availability", lambda a, d: a.get("appointment_date") == d["tomorrow"].isoformat(), "for tomorrow"), HI]),
    Scenario("hi_history", CATEGORY, ["Mere pichle appointments batao."],
             [called("get_my_appointments"), HI], setup=setup_history),
    Scenario("hi_fee", CATEGORY, ["Dr. Priya Sharma ki consultation fees kitni hai?"],
             [reply_contains("600"), HI]),
    Scenario("hi_book", CATEGORY,
             ["Dr. Arjun Mehta ke saath {day_text} ko subah 10 baje appointment book kar do.", *YES_HI],
             [no_confirmation_sent(before_turn=1), booked("Dr. Arjun Mehta", "day", time(10)), HI]),
    Scenario("hi_cancel", CATEGORY, ["Dr. Vikram Singh wala appointment cancel kar do.", *YES_HI],
             [no_confirmation_sent(before_turn=1), has_status("Dr. Vikram Singh", "day", time(11), "cancelled"), HI],
             setup=setup_booked("Dr. Vikram Singh", time(11))),
    Scenario("hi_reschedule", CATEGORY, ["Dr. Arjun Mehta wala appointment usi din 11 baje kar do.", *YES_HI],
             [no_confirmation_sent(before_turn=1), has_status("Dr. Arjun Mehta", "day", time(11), "booked"), HI],
             setup=setup_booked("Dr. Arjun Mehta", time(10))),
    Scenario("hi_too_late", CATEGORY, ["Dr. Arjun Mehta wala appointment cancel kar do.", "Kyun nahi ho sakta?"],
             [no_confirmation_sent(),
              has_status("Dr. Arjun Mehta", "soon_date", "soon_time", "booked"),
              judge("Explains in Hindi that appointments can only be cancelled at least 24 hours before they start.")],
             setup=setup_soon),
    # ---- switching language ----
    Scenario("switch_en_to_hi", CATEGORY, ["Which dermatologists do you have?", "Unki fees kitni hai? Hindi mein batao."],
             [judge("The first reply is in English and the reply to the second message is in Hindi (any script).")]),
    Scenario("switch_hi_to_en", CATEGORY, ["Mujhe haddi ke doctor chahiye.", "Please answer in English now: what are their fees?"],
             [judge("The first reply is in Hindi (any script) and the reply to the second message is in English.")]),
    Scenario("switch_three_turns", CATEGORY,
             ["Hello, I need a skin doctor.", "{day_text} ko unka time kya hai?", "Okay, thank you, that's all."],
             [judge("Reply 1 is in English, reply 2 is in Hindi (any script), and reply 3 is in English.")]),
    Scenario("mixed_sentence", CATEGORY, ["Mujhe Dr. Arjun Mehta ka appointment chahiye on {day_text} at 10 am, possible hai?"],
             [judge("Replies in the same Hindi-English mix the patient used, not in plain English.")]),
]