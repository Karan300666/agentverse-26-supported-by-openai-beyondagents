import asyncio

import logfire
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.nodes.classifier import classifier_node
from app.core.config import get_settings

settings = get_settings()
logfire.configure(
    token=settings.logfire_token.get_secret_value() if settings.logfire_token else None,
    service_name="classifier-test",
)

CASES = [
    ([HumanMessage("What are your visiting hours?")], "faq", None),
    ([HumanMessage("Which cardiologists do you have?")], "db_retrieval", None),
    ([HumanMessage("Is Dr. Rao free tomorrow?")], "db_retrieval", None),
    ([HumanMessage("Show my past appointments")], "db_retrieval", None),
    ([HumanMessage("Book me with a dermatologist")], "action", "book"),
    ([HumanMessage("Cancel my appointment")], "action", "cancel"),
    ([HumanMessage("Move my appointment to Friday")], "action", "reschedule"),
    (
        [AIMessage("Which time works for you?"), HumanMessage("5 pm tomorrow")],
        "action",
        None,
    ),
    ([HumanMessage("I have a headache and fever, what should I take?")], "clinical", None),
    ([HumanMessage("Hello, how are you?")], "small_talk", None),
    ([HumanMessage("I going to goa")], "clinical", None),
]


async def main():
    for msgs, intent, action in CASES:
        out = await classifier_node({"messages": msgs})
        got_intent = out["intent"].value if out["intent"] else None
        got_action = out["action"].value if out["action"] else None
        ok = got_intent == intent and (action is None or got_action == action)
        print("OK  " if ok else "FAIL", got_intent, got_action, "|", msgs[-1].content)


asyncio.run(main())