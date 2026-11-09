"""Runs one tool call safely: lookup, argument validation, execution, uniform result."""

import json
from typing import Any

import logfire
from pydantic import ValidationError

from app.voice.tools import ToolContext, ToolError, get_tool


def _failure(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "data": None, "error": {"code": code, "message": message}}


def _parse_arguments(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        raise ToolError("invalid_arguments", "Arguments must be valid JSON.") from None
    if not isinstance(parsed, dict):
        raise ToolError("invalid_arguments", "Arguments must be a JSON object.")
    return parsed


async def execute_tool(ctx: ToolContext, tool_name: str, raw_arguments: str) -> dict[str, Any]:
    tool = get_tool(tool_name)
    with logfire.span(
        "voice.tool_call {tool}",
        tool=tool_name,
        access=tool.access.value if tool else None,
        session_id=str(ctx.session_id),
        patient_id=str(ctx.patient.id),
        arguments=raw_arguments[:500],
    ):
        if tool is None:
            logfire.warn("unknown tool requested: {tool}", tool=tool_name)
            return _failure("unknown_tool", "That tool does not exist.")

        try:
            arguments = tool.arguments.model_validate(_parse_arguments(raw_arguments))
        except ToolError as exc:
            return _failure(exc.code, exc.message)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()
            )
            logfire.warn("invalid tool arguments: {problems}", problems=problems)
            return _failure("invalid_arguments", problems)

        try:
            data = await tool.handler(ctx, arguments)
        except ToolError as exc:
            logfire.info("tool refused: {code}", code=exc.code)
            return _failure(exc.code, exc.message)
        except Exception:
            logfire.exception("tool crashed: {tool}", tool=tool_name)
            return _failure("internal_error", "Something went wrong. Please try again.")

        return {"ok": True, "data": data, "error": None}