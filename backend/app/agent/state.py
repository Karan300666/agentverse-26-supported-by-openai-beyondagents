from enum import StrEnum
from typing import TypedDict, Literal

class Intent(StrEnum):
    FAQ = "faq"
    DB_RETRIEVAL = "db_retrieval"
    ACTION = "action"
    CLINICAL = "clinical"
    SMALL_TALK = "small_talk"

class ActionType(StrEnum):
    BOOK = "book"
    CANCEL = "cancel"
    RESCHEDULE = "reschedule"

class AgentState(TypedDict):
    messages: list
    intent: Intent | None
    action: ActionType | None
    reply: str | None