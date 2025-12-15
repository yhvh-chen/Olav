"""LangGraph Studio entry point for OLAV Orchestrator.

This module provides a graph for LangGraph Studio/API server.
Uses the same orchestrator as the CLI but in stateless mode.
"""

import operator
import sys
import time
from typing import Annotated

from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph

# Windows event loop compatibility
if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class OrchestratorState(TypedDict):
    """State schema for LangGraph Studio."""

    messages: Annotated[list[BaseMessage], operator.add]
    workflow_type: str | None
    iteration_count: int
    interrupted: bool
    execution_plan: dict | None


# Lazy initialization of orchestrator
_orchestrator = None


def _get_orchestrator():
    """Lazy load orchestrator to avoid import issues at module load time."""
    global _orchestrator
    if _orchestrator is None:
        from olav.agents.root_agent_orchestrator import WorkflowOrchestrator
        from olav.core.llm import LLMFactory

        llm = LLMFactory.get_chat_model()
        _orchestrator = WorkflowOrchestrator(
            llm=llm,
            checkpointer=None,  # Stateless for Studio
            expert_mode=False,
            use_strategy_optimization=True,
        )
    return _orchestrator


async def route_to_workflow(state: OrchestratorState) -> OrchestratorState:
    """Route user query to appropriate workflow."""
    orchestrator = _get_orchestrator()

    # Extract user message
    messages = state.get("messages", [])
    user_message = ""
    normalized_messages = []

    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role") or msg.get("type") or "user"
            content = msg.get("content", "")
            if role in ("user", "human"):
                normalized_messages.append(HumanMessage(content=content))
                user_message = content
            else:
                normalized_messages.append(AIMessage(content=content))
        elif isinstance(msg, BaseMessage):
            normalized_messages.append(msg)
            if msg.type == "human":
                user_message = msg.content

    if not user_message:
        return {
            **state,
            "messages": [AIMessage(content="No user query detected")],
        }

    # Generate thread_id
    thread_id = f"studio-{int(time.time())}"

    # Route to workflow
    result = await orchestrator.route(user_message, thread_id)

    # Extract messages from result
    result_data = result.get("result", {})
    if "messages" in result_data:
        output_messages = result_data["messages"]
    elif result.get("final_message"):
        output_messages = [*normalized_messages, AIMessage(content=result["final_message"])]
    else:
        output_messages = normalized_messages

    return {
        **state,
        "workflow_type": result.get("workflow_type"),
        "messages": output_messages,
        "interrupted": result.get("interrupted", False),
        "execution_plan": result.get("execution_plan"),
    }


def _build_graph():
    """Build the LangGraph StateGraph."""
    graph_builder = StateGraph(OrchestratorState)
    graph_builder.add_node("route_to_workflow", route_to_workflow)
    graph_builder.set_entry_point("route_to_workflow")
    graph_builder.add_edge("route_to_workflow", END)
    return graph_builder.compile()


# Export compiled graph for LangGraph Studio
graph = _build_graph()

__all__ = ["OrchestratorState", "graph"]
