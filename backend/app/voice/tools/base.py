"""Tool framework: every tool the voice model can call is defined and registered here."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient


class Access(StrEnum):
    PUBLIC = "public"  # read-only hospital information, no patient data
    PATIENT = "patient"  # reads the calling patient's own data
    WRITE = "write"  # changes data (book, cancel, reschedule)


class ToolArguments(BaseModel):
    """Base for all argument models: unknown fields are rejected, never ignored."""

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ToolContext:
    """Everything a handler may use. The patient comes from the verified session, never the model."""

    db: AsyncSession
    patient: Patient
    session_id: uuid.UUID


class ToolError(Exception):
    """A business-rule failure the model should hear about (not a crash)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    access: Access
    arguments: type[ToolArguments]
    handler: Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]

    def definition(self) -> dict[str, Any]:
        """The tool definition sent to the Realtime model."""
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.arguments.model_json_schema(),
        }


_TOOLS: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    if tool.name in _TOOLS:
        raise ValueError(f"Tool '{tool.name}' is already registered")
    _TOOLS[tool.name] = tool
    return tool


def get_tool(name: str) -> Tool | None:
    return _TOOLS.get(name)


def all_tools() -> list[Tool]:
    return list(_TOOLS.values())