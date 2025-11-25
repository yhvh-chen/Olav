"""OpenSearch RAG tools for schema and document search."""

import logging
from typing import Any

from langchain_core.tools import tool

from olav.core.memory import OpenSearchMemory

logger = logging.getLogger(__name__)


class OpenSearchRAGTool:
    """RAG tools for searching OpenConfig/SuzieQ schemas and documentation."""

    def __init__(self, memory: OpenSearchMemory | None = None) -> None:
        """Initialize OpenSearch RAG tool.

        Args:
            memory: OpenSearch memory instance
        """
        self.memory = memory or OpenSearchMemory()

    def search_openconfig_schema(
        self,
        intent: str,
        device_type: str = "network-instance",
    ) -> list[dict[str, Any]]:
        """Search OpenConfig YANG schema for XPaths matching user intent.

        Use this tool to find OpenConfig XPaths for configuration tasks.
        It searches the openconfig-schema index built from YANG models.

        Args:
            intent: Natural language description of what you want to configure
                    Examples: "change BGP router ID", "add VLAN interface", "configure OSPF area"
            device_type: OpenConfig module type (network-instance, interfaces, routing-policy)

        Returns:
            List of matching XPaths with descriptions and examples

        Example:
            >>> search_openconfig_schema("configure BGP AS number", "network-instance")
            [
                {
                    "xpath": "/network-instances/network-instance/protocols/protocol/bgp/global/config/as",
                    "description": "Local autonomous system number",
                    "type": "uint32",
                    "example": {"as": 65000}
                }
            ]
        """
        # Semantic search query - simplified for demo
        query = {
            "bool": {
                "must": [
                    {"match": {"description": intent}},
                    {"term": {"module": device_type}},
                ],
            },
        }

        return self.memory.search_schema(
            index="openconfig-schema",
            query=query,
            size=5,
        )

    def search_episodic_memory(
        self,
        intent: str,
    ) -> list[dict[str, Any]]:
        """Search episodic memory for previously successful intent→XPath mappings.

        This searches the learning index for historical success patterns. Use this
        BEFORE search_openconfig_schema to leverage past experience.

        Args:
            intent: User intent to search for

        Returns:
            List of successful historical mappings with context

        Example:
            >>> search_episodic_memory("configure BGP neighbor")
            [
                {
                    "intent": "add BGP neighbor 192.168.1.1 AS 65001",
                    "xpath": "/network-instances/.../neighbors/neighbor[neighbor-address=192.168.1.1]/config",
                    "success": true,
                    "context": {"device": "router1", "timestamp": "2024-01-15T10:30:00Z"}
                }
            ]
        """
        query = {
            "bool": {
                "must": [
                    {"match": {"intent": intent}},
                    {"term": {"success": True}},
                ],
            },
        }

        return self.memory.search_schema(
            index="olav-episodic-memory",
            query=query,
            size=3,
        )


# Create global instance
_opensearch_rag_tool = OpenSearchRAGTool()


# Wrap methods with @tool decorator to expose to LLM
@tool
async def search_openconfig_schema(
    intent: str,
    device_type: str = "network-instance",
) -> list[dict[str, Any]]:
    """Search OpenConfig YANG schema for XPaths matching user intent.

    Use this tool to find OpenConfig XPaths for configuration tasks.
    It searches the openconfig-schema index built from YANG models.

    Args:
        intent: Natural language description of what you want to configure
                Examples: "change BGP router ID", "add VLAN interface", "configure OSPF area"
        device_type: OpenConfig module type (network-instance, interfaces, routing-policy)

    Returns:
        List of matching XPaths with descriptions and examples

    Example:
        >>> search_openconfig_schema("configure BGP AS number", "network-instance")
        [
            {
                "xpath": "/network-instances/network-instance/protocols/protocol/bgp/global/config/as",
                "description": "Local autonomous system number",
                "type": "uint32",
                "example": {"as": 65000}
            }
        ]
    """
    # Semantic search query - simplified for demo
    query = {
        "bool": {
            "must": [
                {"match": {"description": intent}},
                {"term": {"module": device_type}},
            ],
        },
    }

    return await _opensearch_rag_tool.memory.search_schema(
        index="openconfig-schema",
        query=query,
        size=5,
    )


@tool
async def search_episodic_memory(
    intent: str,
) -> list[dict[str, Any]]:
    """Search episodic memory for previously successful intent→XPath mappings.

    This searches the learning index for historical success patterns. Use this
    BEFORE search_openconfig_schema to leverage past experience.

    Args:
        intent: User intent to search for

    Returns:
        List of successful historical mappings with context

    Example:
        >>> search_episodic_memory("configure BGP neighbor")
        [
            {
                "intent": "add BGP neighbor 192.168.1.1 AS 65001",
                "xpath": "/network-instances/.../neighbors/neighbor[neighbor-address=192.168.1.1]/config",
                "success": true,
                "context": {"device": "router1", "timestamp": "2024-01-15T10:30:00Z"}
            }
        ]
    """
    query = {
        "bool": {
            "must": [
                {"match": {"intent": intent}},
                {"term": {"success": True}},
            ],
        },
    }

    return await _opensearch_rag_tool.memory.search_schema(
        index="olav-episodic-memory",
        query=query,
        size=3,
    )
