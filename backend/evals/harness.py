"""Runs one scenario as a text conversation with the production Realtime model (same
instructions and tools). Tools run for real inside a transaction that is rolled back."""

import asyncio
import json
import random
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import logfire
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.routes.voice import _LIMIT_ERRORS
from app.core.config import get_settings
from app.models.patient import Patient
from app.services.doctor_service import now_ist
from app.voice import realtime
from app.voice import session as voice_sessions
from app.voice.tool_executor import execute_tool
from app.voice.tools import ToolContext
from evals.checks import GLOBAL_CHECKS
from evals.models import CheckResult, EvalContext, Scenario, ToolCall, Transcript, Turn

MAX_TOOL_ROUNDS = 8
EVENT_TIMEOUT_SECONDS = 60


def common_data() -> dict[str, Any]:
    """Dates every scenario can use. `day` is the first weekday at least 2 days ahead,
    so it is inside the booking window and outside the 24-hour change rule."""
    today = now_ist().date()
    day = today + timedelta(days=2)
    while day.weekday() > 4:
        day += timedelta(days=1)
    far_day = today + timedelta(days=14)
    past_day = today - timedelta(days=1)

    def text(d):
        return f"{d:%A}, {d.day} {d:%B}"

    return {
        "today": today,
        "tomorrow": today + timedelta(days=1),
        "day": day,
        "day_text": text(day),
        "day_weekday": f"{day:%A}",
        "far_day": far_day,
        "far_text": text(far_day),
        "past_day": past_day,
        "past_text": text(past_day),
    }


def random_test_phone() -> str:
    return f"1{random.randint(0, 999_999_999):09d}"  # real Indian numbers never start with 1


@asynccontextmanager
async def rolled_back_session():
    engine = create_async_engine(
        get_settings().async_database_url,
        poolclass=NullPool,
        connect_args={"ssl": True, "statement_cache_size": 0},
    )
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            session = AsyncSession(
                bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )
            try:
                yield session
            finally:
                await session.close()
                await outer.rollback()
    finally:
        await engine.dispose()


def _session_config() -> dict[str, Any]:
    config = realtime.build_session_config()
    config.pop("audio", None)
    config.pop("model", None)  # the model is chosen when connecting
    config["output_modalities"] = ["text"]
    return config


async def _next_response(conn) -> dict[str, Any]:
    while True:
        event = await asyncio.wait_for(conn.recv(), EVENT_TIMEOUT_SECONDS)
        if event.type == "error":
            raise RuntimeError(f"Realtime error: {event.error.message}")
        if event.type == "response.done":
            response = event.response.model_dump()
            if response.get("status") != "completed":
                raise RuntimeError(f"Response {response.get('status')}: {response.get('status_details')}")
            return response


def _split_output(response: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    texts, calls = [], []
    for item in response.get("output") or []:
        if item.get("type") == "message":
            for part in item.get("content") or []:
                text = part.get("text") or part.get("transcript")
                if text:
                    texts.append(text)
        elif item.get("type") == "function_call":
            calls.append(item)
    return texts, calls


def _parse_arguments(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_raw": raw}
    return parsed if isinstance(parsed, dict) else {"_raw": raw}


async def _run_tool(tool_ctx: ToolContext, voice_session, name: str, raw: str) -> dict[str, Any]:
    """The same path as POST /voice/tool-call: rate limit first, then the executor."""
    limit = voice_sessions.try_acquire_tool_call(voice_session)
    if limit is not None:
        return {"ok": False, "data": None, "error": _LIMIT_ERRORS[limit].model_dump()}
    return await execute_tool(tool_ctx, name, raw)


async def _converse(
    client: AsyncOpenAI, model: str, tool_ctx: ToolContext, voice_session, messages: list[str]
) -> Transcript:
    transcript = Transcript()
    async with client.realtime.connect(model=model) as conn:
        await conn.session.update(session=_session_config())
        for message in messages:
            turn = Turn(user=message)
            transcript.turns.append(turn)
            await conn.conversation.item.create(
                item={
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": message}],
                }
            )
            for _ in range(MAX_TOOL_ROUNDS):
                await conn.response.create()
                texts, calls = _split_output(await _next_response(conn))
                turn.replies.extend(texts)
                if not calls:
                    break
                for call in calls:
                    name = call.get("name", "")
                    raw = call.get("arguments") or "{}"
                    result = await _run_tool(tool_ctx, voice_session, name, raw)
                    turn.tool_calls.append(ToolCall(name, _parse_arguments(raw), result))
                    await conn.conversation.item.create(
                        item={
                            "type": "function_call_output",
                            "call_id": call["call_id"],
                            "output": json.dumps(result),
                        }
                    )
            else:
                turn.replies.append("[eval: stopped after too many tool rounds]")
    return transcript


async def run_scenario(
    scenario: Scenario, client: AsyncOpenAI, judge_model: str
) -> tuple[list[CheckResult], Transcript]:
    settings = get_settings()
    original_limit = settings.max_tool_calls_per_minute

    with logfire.span("eval {scenario}", scenario=scenario.id):
        async with rolled_back_session() as db:
            patient = Patient(name="Eval Patient", age=35, phone=random_test_phone())
            db.add(patient)
            await db.commit()

            data = common_data()
            if scenario.setup:
                data.update(await scenario.setup(db, patient, data))

            if scenario.tool_calls_per_minute is not None:
                settings.max_tool_calls_per_minute = scenario.tool_calls_per_minute
            session_id = voice_sessions.create_session(patient.id)
            try:
                voice_session = voice_sessions.get_session(session_id)
                tool_ctx = ToolContext(db=db, patient=patient, session_id=session_id)
                messages = [m.format(**data) for m in scenario.turns]
                transcript = await _converse(
                    client, settings.realtime_model, tool_ctx, voice_session, messages
                )
            finally:
                voice_sessions.end_session(session_id)
                settings.max_tool_calls_per_minute = original_limit

            ctx = EvalContext(db, patient, data, transcript, client, judge_model)
            results = []
            for check in [*scenario.checks, *GLOBAL_CHECKS]:
                try:
                    passed, detail = await check.run(ctx)
                except Exception as exc:
                    passed, detail = False, f"check crashed: {exc!r}"
                results.append(CheckResult(check.name, passed, detail))

    return results, transcript