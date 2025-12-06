"""Shared components across all modes.

Components:
    - ToolRegistry: Unified tool management
    - HITLMiddleware: Human-in-the-loop approval
    - Confidence: Confidence scoring utilities
    - DebugContext: Debug mode instrumentation

Tools (100% shared):
    - suzieq_query, suzieq_schema_search
    - netbox_api_call
    - netconf_*, cli_*
    - opensearch_*, kb_search
"""
