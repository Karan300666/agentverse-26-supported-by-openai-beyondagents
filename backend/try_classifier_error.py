import asyncio

from langchain_core.messages import HumanMessage

from app.agent.nodes.classifier import _classify


async def main():
    for text in ["Hello!"]:
        print(text, "->", await _classify({"messages": [HumanMessage(text)]}))


asyncio.run(main())