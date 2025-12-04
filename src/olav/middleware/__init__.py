"""OLAV Middleware - 自动注入工具说明到 Prompt。

Middleware 模式借鉴自 deepagents 架构，实现工具说明的自动注入，
使得基础 Prompt 可以保持简短（<20行），同时保证工具使用的一致性。

Usage:
    from olav.middleware import tool_middleware
    
    enriched_prompt = tool_middleware.enrich_prompt(
        base_prompt="你是网络诊断专家...",
        tools=[suzieq_query, netconf_tool]
    )
"""

from olav.middleware.tool_middleware import ToolMiddleware, tool_middleware

__all__ = ["ToolMiddleware", "tool_middleware"]
