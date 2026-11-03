"""Input guardrail node: runs the NeMo input rails and records the result in state."""

import logfire
from langchain_core.messages import AIMessage

from app.agent.guardrails import check_input
from app.agent.state import AgentState

REFUSAL_MESSAGE = (
    "I'm sorry, I can't help with that. I can help you find doctors, "
    "book, reschedule or cancel appointments, and answer questions about the hospital."
)


async def validator_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    with logfire.span("agent.validator"):
        # Reset per-turn fields so nothing stale carries over from the previous turn.
        reset = {"intent": None, "action": None, "reply": ""}

        if not messages or isinstance(messages[-1], AIMessage):
            logfire.warn("validator: no user message to check")
            return {**reset, "is_valid": False, "rejection_reason": "empty", "reply": REFUSAL_MESSAGE}

        try:
            check = await check_input(messages)
        except Exception:
            logfire.exception("validator: input rails failed, rejecting (fail closed)")
            return {**reset, "is_valid": False, "rejection_reason": "guard_error", "reply": REFUSAL_MESSAGE}

        logfire.info(
            "input guardrails: valid={is_valid} category={category}",
            is_valid=check.is_valid,
            category=check.category,
        )
        if not check.is_valid:
            return {**reset, "is_valid": False, "rejection_reason": check.category, "reply": REFUSAL_MESSAGE}
        return {**reset, "is_valid": True, "rejection_reason": None}