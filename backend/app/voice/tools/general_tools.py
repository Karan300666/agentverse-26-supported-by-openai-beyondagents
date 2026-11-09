"""General tools with no patient data."""

from typing import Any

from app.services import doctor_service
from app.voice.tools.base import Access, Tool, ToolArguments, ToolContext, register


class NoArguments(ToolArguments):
    pass


async def _get_current_datetime(ctx: ToolContext, args: NoArguments) -> dict[str, Any]:
    now = doctor_service.now_ist()
    return {
        "date": now.date().isoformat(),
        "weekday": now.strftime("%A"),
        "time": now.strftime("%H:%M"),
        "timezone": "Asia/Kolkata",
    }


register(
    Tool(
        name="get_current_datetime",
        description=(
            "Get today's date, weekday and the current time at the hospital (IST). "
            "Use it to work out what 'today', 'tomorrow' or 'next Monday' mean."
        ),
        access=Access.PUBLIC,
        arguments=NoArguments,
        handler=_get_current_datetime,
    )
)