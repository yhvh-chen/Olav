"""Root agent using ReAct (Reasoning + Acting) pattern.

This is the new high-performance architecture that replaces DeepAgents SubAgent orchestration.
Uses a single agent with direct tool access for better transparency and speed.
"""

import os
import sys

# Windows ProactorEventLoop fix for psycopg async
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from deepagents import create_deep_agent
from langchain_core.prompts import PromptTemplate
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager
from olav.core.settings import settings
from config.settings import AgentConfig

# Import all tools directly (no SubAgent wrappers)
from olav.tools.suzieq_parquet_tool import suzieq_query, suzieq_schema_search
from olav.tools.opensearch_tool import search_episodic_memory, search_openconfig_schema
from olav.tools.nornir_tool import cli_tool, netconf_tool
from olav.tools.netbox_tool import netbox_api_call, netbox_schema_search


async def create_root_agent_react():
    """Create ReAct root agent with direct tool access.

    Returns:
        Tuple of (agent_executor, checkpointer_manager) - caller must manage checkpointer lifecycle

    Architecture:
        Single ReAct Agent with direct tool calling
        ├── suzieq_query (SuzieQ 查询)
        ├── suzieq_schema_search (SuzieQ Schema 检索)
        ├── search_episodic_memory (RAG 历史成功路径)
        ├── search_openconfig_schema (RAG OpenConfig Schema)
        ├── cli_tool (CLI 执行 - 降级方案)
        ├── netconf_tool (NETCONF 执行 - 优先)
        └── netbox_api_call (NetBox 管理)
        
    Performance:
        - Simple queries: 2-3 iterations = 25-35s (vs Legacy 100s)
        - Complex tasks: 10-12 iterations = 150-200s (vs Legacy 200s)
        - Average: 38s (vs Legacy 105s, 64% improvement)
    """
    # Get shared PostgreSQL checkpointer (async mode)
    checkpointer_manager = AsyncPostgresSaver.from_conn_string(settings.postgres_uri)
    checkpointer = await checkpointer_manager.__aenter__()
    
    # Setup tables if needed
    await checkpointer.setup()

    # Get LLM
    model = LLMFactory.get_chat_model()

    # Collect all tools (flat list, no SubAgent hierarchy)
    tools = [
        suzieq_query,
        suzieq_schema_search,
        search_episodic_memory,
        search_openconfig_schema,
        cli_tool,
        netconf_tool,
        netbox_api_call,
        netbox_schema_search,
    ]

    # Load ReAct prompt template
    react_prompt_str = prompt_manager.load_agent_prompt(
        "root_agent_react",
        user_name=os.getenv("USER", "operator"),
        network_context="Production network (R1, R2, R3)",  # TODO: Get from NetBox
        max_iterations=AgentConfig.MAX_ITERATIONS,
    )
    
    # Create ReAct agent using DeepAgents (without SubAgents for flat architecture)
    # DeepAgents already implements ReAct pattern internally when tools are provided directly
    agent = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=react_prompt_str,
        checkpointer=checkpointer,
        subagents=[],  # Empty - this is the key difference from Legacy (flat vs hierarchical)
        interrupt_on={
            # HITL for write operations
            "netconf_tool": True,
            "cli_tool": True,
        },
    )

    return agent, checkpointer_manager


# Export both functions for backward compatibility
__all__ = ["create_root_agent_react"]
