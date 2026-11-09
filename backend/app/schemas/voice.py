import uuid
from typing import Annotated, Any

from pydantic import BaseModel, StringConstraints


class VoiceSessionRead(BaseModel):
    session_id: uuid.UUID
    client_secret: str  # short-lived key the browser uses to connect to OpenAI


class ToolCallRequest(BaseModel):
    session_id: uuid.UUID
    tool_name: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    # The model's arguments exactly as sent (a JSON string); the backend parses and validates them.
    arguments: Annotated[str, StringConstraints(max_length=4000)] = "{}"


class ToolErrorRead(BaseModel):
    code: str
    message: str


class ToolCallResult(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    error: ToolErrorRead | None = None