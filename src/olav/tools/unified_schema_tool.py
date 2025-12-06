# OLAV - Unified Schema Search Tool
# Combines SuzieQ schema and OpenConfig YANG schema search

"""
Unified Schema Search Tool

This tool provides a single entry point for schema discovery:
1. SuzieQ tables/fields (from suzieq-schema OpenSearch index)
2. OpenConfig YANG XPaths (from openconfig-schema OpenSearch index)

The LLM uses this to understand what data/config paths are available
before making queries or configuration changes.

Usage:
    from olav.tools.unified_schema_tool import unified_schema_search

    # Search both SuzieQ and OpenConfig
    result = await unified_schema_search("BGP configuration")

    # Search specific schema
    result = await unified_schema_search("BGP", schema_type="suzieq")
    result = await unified_schema_search("BGP AS number", schema_type="yang")
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain_core.tools import tool

from olav.core.memory import OpenSearchMemory
from olav.core.schema_loader import get_schema_loader

logger = logging.getLogger(__name__)


# Global instances
_schema_loader = get_schema_loader()
_memory: OpenSearchMemory | None = None


def _get_memory() -> OpenSearchMemory:
    """Lazy-load OpenSearch memory."""
    global _memory
    if _memory is None:
        _memory = OpenSearchMemory()
    return _memory


@tool
async def unified_schema_search(
    query: str,
    schema_type: Literal["all", "suzieq", "yang"] = "all",
    max_results: int = 10,
) -> dict[str, Any]:
    """Search network schema for tables, fields, and XPaths.

    This unified tool searches:
    - SuzieQ schema: Tables and fields for network data queries
    - OpenConfig YANG: XPaths for device configuration

    Always call this BEFORE making queries or config changes to discover
    available data paths and their structure.

    Args:
        query: Natural language description of what you're looking for.
               Examples: "BGP sessions", "interface IP addresses", "OSPF neighbors"
        schema_type: Which schema to search:
                    - "all": Search both SuzieQ and YANG (default)
                    - "suzieq": Only SuzieQ tables/fields
                    - "yang": Only OpenConfig XPaths
        max_results: Maximum results per schema type (default: 10)

    Returns:
        Dictionary with schema search results:
        {
            "suzieq": {
                "tables": ["bgp", "routes"],
                "bgp": {"fields": [...], "methods": [...], "description": "..."},
                ...
            },
            "yang": {
                "xpaths": [
                    {"xpath": "/network-instances/.../bgp/...", "description": "...", "type": "..."},
                    ...
                ]
            },
            "query": "BGP sessions",
            "schema_types_searched": ["suzieq", "yang"]
        }

    Example:
        >>> await unified_schema_search("BGP neighbor state")
        {
            "suzieq": {
                "tables": ["bgp"],
                "bgp": {
                    "fields": ["hostname", "peer", "state", "asn", "vrf"],
                    "methods": ["get", "summarize"],
                    "description": "BGP protocol information"
                }
            },
            "yang": {
                "xpaths": [
                    {
                        "xpath": "/network-instances/.../bgp/neighbors/neighbor/state",
                        "description": "State parameters for BGP neighbor",
                        "type": "container"
                    }
                ]
            }
        }
    """
    result: dict[str, Any] = {
        "query": query,
        "schema_types_searched": [],
    }

    # Search SuzieQ schema
    if schema_type in ("all", "suzieq"):
        try:
            suzieq_result = await _search_suzieq_schema(query, max_results)
            result["suzieq"] = suzieq_result
            result["schema_types_searched"].append("suzieq")
        except Exception as e:
            logger.warning(f"SuzieQ schema search failed: {e}")
            result["suzieq"] = {"error": str(e), "tables": []}

    # Search OpenConfig YANG schema
    if schema_type in ("all", "yang"):
        try:
            yang_result = await _search_yang_schema(query, max_results)
            result["yang"] = yang_result
            result["schema_types_searched"].append("yang")
        except Exception as e:
            logger.warning(f"YANG schema search failed: {e}")
            result["yang"] = {"error": str(e), "xpaths": []}

    return result


async def _search_suzieq_schema(query: str, max_results: int) -> dict[str, Any]:
    """Search SuzieQ schema for matching tables and fields.

    Uses the schema_loader which queries OpenSearch suzieq-schema index.
    """
    # Load schema from OpenSearch
    suzieq_schema = await _schema_loader.load_suzieq_schema()

    # Keyword matching for tables
    keywords = query.lower().split()

    # Score tables by keyword matches
    table_scores: list[tuple[str, int, dict[str, Any]]] = []

    for table, info in suzieq_schema.items():
        score = 0
        table_lower = table.lower()
        desc_lower = info.get("description", "").lower()
        fields_str = " ".join(info.get("fields", [])).lower()

        for keyword in keywords:
            if keyword in table_lower:
                score += 3  # Exact table name match
            if keyword in desc_lower:
                score += 2  # Description match
            if keyword in fields_str:
                score += 1  # Field name match

        if score > 0:
            table_scores.append((table, score, info))

    # Sort by score descending
    table_scores.sort(key=lambda x: x[1], reverse=True)

    # Take top results
    top_tables = table_scores[:max_results]

    # If no matches, return some common tables
    if not top_tables:
        common = ["interfaces", "device", "bgp", "routes", "vlan"]
        top_tables = [
            (t, 0, suzieq_schema.get(t, {}))
            for t in common
            if t in suzieq_schema
        ]

    # Build result
    result: dict[str, Any] = {
        "tables": [t[0] for t in top_tables],
    }

    for table, score, info in top_tables:
        result[table] = {
            "fields": info.get("fields", []),
            "methods": info.get("methods", ["get", "summarize"]),
            "description": info.get("description", ""),
            "relevance_score": score,
        }

    return result


async def _search_yang_schema(query: str, max_results: int) -> dict[str, Any]:
    """Search OpenConfig YANG schema for matching XPaths.

    Uses OpenSearch openconfig-schema index with semantic search.
    """
    memory = _get_memory()

    # Build OpenSearch query
    os_query = {
        "bool": {
            "should": [
                {"match": {"description": {"query": query, "boost": 2.0}}},
                {"match": {"xpath": {"query": query, "boost": 1.5}}},
                {"match": {"module": {"query": query, "boost": 1.0}}},
            ],
            "minimum_should_match": 1,
        },
    }

    try:
        # Execute search
        hits = await memory.search_schema(
            index="openconfig-schema",
            query=os_query,
            size=max_results,
        )

        # Format results
        xpaths = []
        for hit in hits:
            source = hit.get("_source", {})
            xpaths.append({
                "xpath": source.get("xpath", ""),
                "description": source.get("description", ""),
                "type": source.get("type", "unknown"),
                "module": source.get("module", ""),
                "config": source.get("config", True),  # True = config, False = state
                "score": hit.get("_score", 0),
            })

        return {
            "xpaths": xpaths,
            "total_found": len(xpaths),
        }

    except Exception as e:
        logger.error(f"OpenSearch YANG search failed: {e}")
        return {
            "xpaths": [],
            "error": str(e),
        }


@tool
async def yang_xpath_lookup(
    xpath_pattern: str,
    include_children: bool = False,
    max_results: int = 20,
) -> dict[str, Any]:
    """Look up OpenConfig YANG XPath details.

    Use this when you have a specific XPath pattern and want to find
    its full definition, children, or related paths.

    Args:
        xpath_pattern: XPath or XPath pattern to look up.
                      Examples: "/interfaces/interface/config", "bgp/global"
        include_children: Whether to include child XPaths (default: False)
        max_results: Maximum results to return (default: 20)

    Returns:
        Dictionary with matching XPaths and their details:
        {
            "xpaths": [
                {
                    "xpath": "/openconfig-interfaces:interfaces/interface/config/name",
                    "description": "The name of the interface",
                    "type": "leafref",
                    "config": true
                },
                ...
            ]
        }
    """
    memory = _get_memory()

    # Build query for XPath prefix/wildcard match
    if include_children:
        # Prefix match to get children
        os_query = {
            "bool": {
                "should": [
                    {"prefix": {"xpath": xpath_pattern}},
                    {"wildcard": {"xpath": f"*{xpath_pattern}*"}},
                ],
                "minimum_should_match": 1,
            },
        }
    else:
        # Exact or partial match
        os_query = {
            "bool": {
                "should": [
                    {"match_phrase": {"xpath": xpath_pattern}},
                    {"wildcard": {"xpath": f"*{xpath_pattern}*"}},
                ],
                "minimum_should_match": 1,
            },
        }

    try:
        hits = await memory.search_schema(
            index="openconfig-schema",
            query=os_query,
            size=max_results,
        )

        xpaths = []
        for hit in hits:
            source = hit.get("_source", {})
            xpaths.append({
                "xpath": source.get("xpath", ""),
                "description": source.get("description", ""),
                "type": source.get("type", "unknown"),
                "module": source.get("module", ""),
                "config": source.get("config", True),
                "default": source.get("default", None),
            })

        return {
            "pattern": xpath_pattern,
            "xpaths": xpaths,
            "total_found": len(xpaths),
            "include_children": include_children,
        }

    except Exception as e:
        logger.error(f"XPath lookup failed: {e}")
        return {
            "pattern": xpath_pattern,
            "xpaths": [],
            "error": str(e),
        }
