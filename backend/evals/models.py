"""Data types shared by the eval harness, checks and scenarios."""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient

WRITE_TOOLS = ("book_appointment", "cancel_appointment", "reschedule_appointment")


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]

    @property
    def outcome(self) -> str:
        if self.result.get("ok"):
            return (self.result.get("data") or {}).get("status") or "ok"
        return (self.result.get("error") or {}).get("code", "error")


@dataclass
class Turn:
    user: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    replies: list[str] = field(default_factory=list)

    @property
    def reply(self) -> str:
        return " ".join(r.strip() for r in self.replies if r.strip())


@dataclass
class Transcript:
    turns: list[Turn] = field(default_factory=list)

    def tool_calls(self, turn: int | None = None) -> list[ToolCall]:
        turns = self.turns if turn is None else self.turns[turn : turn + 1]
        return [call for t in turns for call in t.tool_calls]

    def replies(self, turn: int | None = None) -> str:
        turns = self.turns if turn is None else self.turns[turn : turn + 1]
        return " ".join(t.reply for t in turns)

    def as_text(self) -> str:
        lines = []
        for t in self.turns:
            lines.append(f"Patient: {t.user}")
            for c in t.tool_calls:
                args = json.dumps(c.arguments, ensure_ascii=False)
                lines.append(f"[tool] {c.name}({args}) -> {c.outcome}")
            lines.append(f"Assistant: {t.reply or '(no reply)'}")
        return "\n".join(lines)


@dataclass
class EvalContext:
    db: AsyncSession
    patient: Patient
    data: dict[str, Any]
    transcript: Transcript
    judge_client: AsyncOpenAI
    judge_model: str


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Check:
    name: str
    run: Callable[[EvalContext], Awaitable[tuple[bool, str]]]


@dataclass
class Scenario:
    id: str
    category: str
    turns: list[str]  # patient messages; {placeholders} are filled from the scenario data
    checks: list[Check]
    setup: Callable[[AsyncSession, Patient, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None
    tool_calls_per_minute: int | None = None  # temporarily lower the rate limit