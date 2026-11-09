"""One-time confirmation codes. A write tool first proposes, then runs only when called
again with the code, the same session, the same patient and the same arguments."""

import json
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any

CODE_TTL_SECONDS = 300  # 5 minutes


@dataclass(frozen=True)
class _Pending:
    session_id: uuid.UUID
    patient_id: uuid.UUID
    tool_name: str
    arguments_key: str
    expires_at: float


_pending: dict[str, _Pending] = {}


def _key(arguments: dict[str, Any]) -> str:
    return json.dumps(arguments, sort_keys=True, default=str)


def _purge(now: float) -> None:
    for code in [c for c, p in _pending.items() if p.expires_at <= now]:
        del _pending[code]


def create(
    session_id: uuid.UUID, patient_id: uuid.UUID, tool_name: str, arguments: dict[str, Any]
) -> str:
    now = time.monotonic()
    _purge(now)
    code = secrets.token_urlsafe(9)
    _pending[code] = _Pending(
        session_id, patient_id, tool_name, _key(arguments), now + CODE_TTL_SECONDS
    )
    return code


def consume(
    code: str,
    session_id: uuid.UUID,
    patient_id: uuid.UUID,
    tool_name: str,
    arguments: dict[str, Any],
) -> bool:
    """True only if the code exists, is unexpired and matches everything. A code is single-use:
    it is removed even when it does not match."""
    now = time.monotonic()
    _purge(now)
    pending = _pending.pop(code, None)
    if pending is None:
        return False
    return (
        pending.session_id == session_id
        and pending.patient_id == patient_id
        and pending.tool_name == tool_name
        and pending.arguments_key == _key(arguments)
    )