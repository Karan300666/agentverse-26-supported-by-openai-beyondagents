"""In-memory registry of active voice calls. Lost on server restart; no expiry yet."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class VoiceSession:
    id: uuid.UUID
    patient_id: uuid.UUID
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


_sessions: dict[uuid.UUID, VoiceSession] = {}


def create_session(patient_id: uuid.UUID) -> uuid.UUID:
    session = VoiceSession(id=uuid.uuid4(), patient_id=patient_id)
    _sessions[session.id] = session
    return session.id


def get_session(session_id: uuid.UUID) -> VoiceSession | None:
    return _sessions.get(session_id)


def end_session(session_id: uuid.UUID) -> None:
    _sessions.pop(session_id, None)