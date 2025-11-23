"""Run chat with clean encoding."""
import asyncio
import sys

# Fix Windows event loop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from olav.agents.root_agent_orchestrator import create_workflow_orchestrator
from langchain_core.messages import HumanMessage

async def run_chat():
    print("Initializing orchestrator...")
    agent, checkpointer_manager = await create_workflow_orchestrator()
    
    query = "查询全网设备的BGP状态"
    print(f"Sending query: {query}")
    
    config = {"configurable": {"thread_id": "test-encoding-1"}}
    
    async for chunk in agent.astream(
        {"messages": [HumanMessage(content=query)]},
        config=config,
        stream_mode="values"
    ):
        if "messages" in chunk:
            last_msg = chunk["messages"][-1]
            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                print(f"🛠️ Tool Call: {last_msg.tool_calls}")
            if not last_msg.content and not last_msg.tool_calls:
                continue
            print(f"🤖 Response: {last_msg.content[:100]}...")

if __name__ == "__main__":
    asyncio.run(run_chat())
