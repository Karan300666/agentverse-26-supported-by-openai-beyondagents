"""In-memory registry of active voice calls, with expiry and rate limits.
Lost on server restart. Fine for a single process."""

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.core.config import get_settings


class TooManySessionsError(Exception):
    pass


class LimitKind(StrEnum):
    PER_MINUTE = "per_minute"
    TOTAL = "total"


@dataclass
class VoiceSession:
    id: uuid.UUID
    patient_id: uuid.UUID
    expires_at: float  # time.monotonic() value
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    tool_call_times: deque[float] = field(default_factory=deque)
    total_tool_calls: int = 0


_sessions: dict[uuid.UUID, VoiceSession] = {}


def _purge_expired(now: float) -> None:
    for session_id in [sid for sid, s in _sessions.items() if s.expires_at <= now]:
        del _sessions[session_id]


def create_session(patient_id: uuid.UUID) -> uuid.UUID:
    """Create a session, or raise TooManySessionsError if the patient already has too many open."""
    settings = get_settings()
    now = time.monotonic()
    _purge_expired(now)

    open_sessions = sum(1 for s in _sessions.values() if s.patient_id == patient_id)
    if open_sessions >= settings.max_concurrent_sessions_per_patient:
        raise TooManySessionsError

    session = VoiceSession(
        id=uuid.uuid4(),
        patient_id=patient_id,
        expires_at=now + settings.session_max_minutes * 60,
    )
    _sessions[session.id] = session
    return session.id


def get_session(session_id: uuid.UUID) -> VoiceSession | None:
    _purge_expired(time.monotonic())
    return _sessions.get(session_id)


def end_session(session_id: uuid.UUID) -> None:
    _sessions.pop(session_id, None)


def try_acquire_tool_call(session: VoiceSession) -> LimitKind | None:
    """Count one tool call. Returns which limit was hit, or None if the call is allowed.
    Rejected calls are not counted."""
    settings = get_settings()
    now = time.monotonic()

    while session.tool_call_times and now - session.tool_call_times[0] >= 60:
        session.tool_call_times.popleft()

    if session.total_tool_calls >= settings.max_tool_calls_per_session:
        return LimitKind.TOTAL
    if len(session.tool_call_times) >= settings.max_tool_calls_per_minute:
        return LimitKind.PER_MINUTE

    session.tool_call_times.append(now)
    session.total_tool_calls += 1
    return None