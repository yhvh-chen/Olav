"""RAG (Retrieval Augmented Generation) SubAgent factory.

Implements tiered retrieval strategy: Memory -> Schema -> Docs.
Currently wires available tools; docs retrieval can be added later.
"""
from deepagents import SubAgent

from olav.core.prompt_manager import prompt_manager
from olav.tools.opensearch_tool import search_episodic_memory, search_openconfig_schema


def create_rag_subagent() -> SubAgent:
    """Create the RAG SubAgent.

    Provides a default 'priority' context variable to satisfy prompt templates
    that may declare it. If the template does not require it, it is ignored.

    Returns:
        Configured SubAgent for retrieval tasks (read-only, no HITL needed).
    """
    rag_prompt = prompt_manager.load_agent_prompt("rag_agent", priority="normal")
    
    return SubAgent(
        name="rag-searcher",
        description="检索 OpenConfig Schema、历史成功路径、文档",
        system_prompt=rag_prompt,
        tools=[search_episodic_memory, search_openconfig_schema],
        # No interrupt_on - read-only operations
    )
