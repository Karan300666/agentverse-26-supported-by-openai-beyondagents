"""Placeholder branches. Each gets replaced by a real node in its own step."""

import logfire

from app.agent.state import AgentState


def _stub(name: str, reply: str):
    async def node(state: AgentState) -> dict:
        with logfire.span(f"agent.{name}"):
            logfire.info("stub branch reached: {name}", name=name)
            return {"reply": reply}

    return node


faq_node = _stub("faq", "[stub] FAQ branch reached.")
db_retrieval_node = _stub("db_retrieval", "[stub] Database retrieval branch reached.")
action_node = _stub("action", "[stub] Appointment action branch reached.")
clinical_node = _stub("clinical", "[stub] Clinical concern branch reached.")
small_talk_node = _stub("small_talk", "[stub] Small talk branch reached.")