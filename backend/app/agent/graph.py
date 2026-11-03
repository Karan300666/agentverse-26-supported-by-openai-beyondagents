"""LangGraph definition and a helper to run one voice turn."""

import logfire
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agent.nodes import stubs
from app.agent.nodes.classifier import classifier_node
from app.agent.nodes.response import response_node
from app.agent.nodes.validator import validator_node
from app.agent.state import AgentState, Intent


def route_after_validator(state: AgentState) -> str:
    return "classifier" if state.get("is_valid") else "respond"


def route_after_classifier(state: AgentState) -> str:
    intent = state.get("intent")
    if intent is None:  # classifier failed; it already set an error reply
        return "respond"
    return intent.value


def build_graph(checkpointer: BaseCheckpointSaver):
    graph = StateGraph(AgentState)

    graph.add_node("validator", validator_node)
    graph.add_node("classifier", classifier_node)
    graph.add_node(Intent.FAQ.value, stubs.faq_node)
    graph.add_node(Intent.DB_RETRIEVAL.value, stubs.db_retrieval_node)
    graph.add_node(Intent.ACTION.value, stubs.action_node)
    graph.add_node(Intent.CLINICAL.value, stubs.clinical_node)
    graph.add_node(Intent.SMALL_TALK.value, stubs.small_talk_node)
    graph.add_node("respond", response_node)

    graph.add_edge(START, "validator")
    graph.add_conditional_edges(
        "validator",
        route_after_validator,
        {"classifier": "classifier", "respond": "respond"},
    )
    graph.add_conditional_edges(
        "classifier",
        route_after_classifier,
        {**{i.value: i.value for i in Intent}, "respond": "respond"},
    )
    for intent in Intent:
        graph.add_edge(intent.value, "respond")
    graph.add_edge("respond", END)

    return graph.compile(checkpointer=checkpointer)


async def run_turn(graph, *, session_id: str, patient_id: str, text: str) -> str:
    """Run one user utterance through the graph and return the text to speak."""
    config = {"configurable": {"thread_id": session_id}}
    with logfire.span("agent.turn", session_id=session_id, patient_id=patient_id):
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=text)], "patient_id": patient_id},
            config=config,
        )
        return result["reply"]