"""LangChain tools for network operations.

This module provides both:
1. LangChain @tool decorated functions (for LangGraph ToolNode)
2. BaseTool classes that register with ToolRegistry (for Strategies)

Tool Organization:
- datetime_tool: Time utilities
- netbox_tool: NetBox API integration (NetBoxAPITool class)
- nornir_tool: NETCONF/CLI execution (NetconfTool, CLITool)
- opensearch_tool: Schema and document search
- suzieq_tool: BaseTool classes for ToolRegistry
- suzieq_parquet_tool: @tool functions for Parquet queries (direct import)
- suzieq_analyzer_tool: Quick Analyzer tools (path_trace, health_check, topology)
- indexing_tool: Document indexing utilities (direct import)
- kb_tools: Knowledge Base tools (Agentic RAG) - kb_search, kb_index_report

Usage:
    # For ToolRegistry-based access
    from olav.tools.base import ToolRegistry
    tool = ToolRegistry.get_tool("suzieq_query")

    # For LangGraph ToolNode (direct @tool functions)
    from olav.tools.suzieq_parquet_tool import suzieq_query, suzieq_schema_search
    
    # For Quick Analyzer
    from olav.tools.suzieq_analyzer_tool import (
        suzieq_path_trace, suzieq_health_check, suzieq_topology_analyze
    )
    
    # For Agentic RAG (Knowledge Base)
    from olav.tools.kb_tools import kb_search, kb_index_report
"""

# Import all tool modules to trigger ToolRegistry.register() side effects
from olav.tools import (
    datetime_tool,
    netbox_tool,
    nornir_tool,
    opensearch_tool,
    suzieq_tool,
)
from olav.tools.base import BaseTool, ToolRegistry

# Re-export commonly used classes
from olav.tools.netbox_tool import NetBoxAPITool

# Re-export Quick Analyzer tools
from olav.tools.suzieq_analyzer_tool import (
    suzieq_health_check,
    suzieq_path_trace,
    suzieq_topology_analyze,
)

# Re-export Knowledge Base tools (Agentic RAG)
from olav.tools.kb_tools import kb_index_report, kb_search

# Note: The following are @tool functions (not BaseTool classes):
# - suzieq_parquet_tool: suzieq_query, suzieq_schema_search
# - indexing_tool: index_document, index_directory, search_indexed_documents
# Import them directly when needed for LangGraph ToolNode.

__all__ = [
    "BaseTool",
    # Classes
    "NetBoxAPITool",
    "ToolRegistry",
    # Quick Analyzer tools
    "suzieq_path_trace",
    "suzieq_health_check",
    "suzieq_topology_analyze",
    # Knowledge Base tools (Agentic RAG)
    "kb_search",
    "kb_index_report",
    # Modules
    "datetime_tool",
    "netbox_tool",
    "nornir_tool",
    "opensearch_tool",
    "suzieq_tool",
]
