"""Helpers shared by agent nodes."""

from langchain_core.messages import AnyMessage, HumanMessage


def format_excerpt(messages: list[AnyMessage], limit: int) -> str:
    """Render the last `limit` messages as text, marking the final one as LATEST."""
    recent = messages[-limit:]
    lines = []
    for i, m in enumerate(recent):
        role = "User" if isinstance(m, HumanMessage) else "Assistant"
        tag = " (LATEST)" if i == len(recent) - 1 else ""
        lines.append(f"{role}{tag}: {m.content}")
    return "\n".join(lines)