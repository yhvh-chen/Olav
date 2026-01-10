"""Task delegation tools for OLAV workflows.

Provides tools to delegate tasks to specialized subagents.
"""
from langchain_core.tools import tool

from olav.core.subagent_manager import get_subagent_middleware
from olav.tools.network import list_devices, nornir_execute


# Global subagent middleware instance
_subagent_middleware = None


def get_task_middleware():
    """Get or create subagent middleware instance."""
    global _subagent_middleware

    if _subagent_middleware is None:
        # Tools available to subagents
        tools = [
            list_devices,
            nornir_execute,
        ]

        _subagent_middleware = get_subagent_middleware(tools=tools)

    return _subagent_middleware


@tool
def delegate_task(
    subagent_type: str,
    task_description: str,
) -> str:
    """Delegate a task to a specialized subagent.

    Args:
        subagent_type: Type of subagent ("macro-analyzer" or "micro-analyzer")
        task_description: Detailed description of the task to perform

    Returns:
        Subagent execution result

    Examples:
        >>> delegate_task("macro-analyzer", "Trace path from R1 to R3")
        "Macro analysis complete: Path is R1 → R2 → R3"
    """
    try:
        middleware = get_task_middleware()

        if hasattr(middleware, 'subagent_graphs'):
            subagent_graphs = middleware.subagent_graphs

            if subagent_type not in subagent_graphs:
                available = ", ".join(subagent_graphs.keys())
                return f"Error: Unknown subagent type '{subagent_type}'. Available: {available}"

            # Invoke subagent
            subagent_graph = subagent_graphs[subagent_type]

            # Prepare initial state
            initial_state = {
                "messages": [{"role": "user", "content": task_description}],
                "tool_call_id": None,
            }

            # Run subagent
            result = subagent_graph.invoke(initial_state)

            # Extract final message
            if result and "messages" in result:
                final_message = result["messages"][-1]
                return final_message.get("content", "No content from subagent")

            return "Subagent completed but produced no output"

        else:
            return "Error: Subagent middleware not properly configured"

    except Exception as e:
        return f"Error delegating task: {str(e)}"
