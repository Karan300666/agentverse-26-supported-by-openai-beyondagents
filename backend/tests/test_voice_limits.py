import uuid

import pytest

from app.voice import session as vs


def test_one_open_session_per_patient(limits):
    patient = uuid.uuid4()
    first = vs.create_session(patient)
    with pytest.raises(vs.TooManySessionsError):
        vs.create_session(patient)
    vs.create_session(uuid.uuid4())  # a different patient is unaffected
    vs.end_session(first)
    vs.create_session(patient)  # allowed again after hanging up


def test_session_expires_after_the_maximum_length(limits, clock):
    patient = uuid.uuid4()
    session_id = vs.create_session(patient)

    clock.advance(29 * 60)
    assert vs.get_session(session_id) is not None

    clock.advance(2 * 60)  # 31 minutes in
    assert vs.get_session(session_id) is None
    vs.create_session(patient)  # an expired session no longer blocks a new call


def test_per_minute_limit_and_recovery(limits, clock):
    session = vs.get_session(vs.create_session(uuid.uuid4()))
    assert [vs.try_acquire_tool_call(session) for _ in range(3)] == [None, None, None]
    assert vs.try_acquire_tool_call(session) == vs.LimitKind.PER_MINUTE
    assert session.total_tool_calls == 3  # the refused call was not counted

    clock.advance(61)
    assert vs.try_acquire_tool_call(session) is None


def test_total_limit_per_session(limits, clock):
    limits.max_tool_calls_per_minute = 100
    limits.max_tool_calls_per_session = 5
    session = vs.get_session(vs.create_session(uuid.uuid4()))
    for _ in range(5):
        assert vs.try_acquire_tool_call(session) is None
    assert vs.try_acquire_tool_call(session) == vs.LimitKind.TOTAL

    clock.advance(600)  # waiting does not reset the total
    assert vs.try_acquire_tool_call(session) == vs.LimitKind.TOTAL


def test_limits_are_per_session(limits):
    one = vs.get_session(vs.create_session(uuid.uuid4()))
    two = vs.get_session(vs.create_session(uuid.uuid4()))
    for _ in range(3):
        vs.try_acquire_tool_call(one)
    assert vs.try_acquire_tool_call(one) == vs.LimitKind.PER_MINUTE
    assert vs.try_acquire_tool_call(two) is None