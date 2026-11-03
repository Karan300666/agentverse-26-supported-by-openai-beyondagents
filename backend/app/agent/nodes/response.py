"""Final node: stores the reply in the conversation history. Output guardrail goes here later."""

import logfire
from langchain_core.messages import AIMessage

from app.agent.state import AgentState


async def response_node(state: AgentState) -> dict:
    with logfire.span("agent.response"):
        reply = state.get("reply") or "Sorry, something went wrong. Please try again."
        logfire.info("final reply ready", reply=reply)
        return {"reply": reply, "messages": [AIMessage(content=reply)]}