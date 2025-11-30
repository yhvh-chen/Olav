"""Document search tool for RAG retrieval.

Provides LangChain tool interface for searching indexed documents
in the olav-docs OpenSearch index.

This tool enables agents to retrieve relevant documentation
(vendor manuals, RFCs, configuration guides) to answer questions.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain_core.tools import tool

from olav.etl.document_indexer import DocumentIndexer, EmbeddingService

logger = logging.getLogger(__name__)


class DocumentSearchTool:
    """Tool for searching indexed vendor documentation.

    Searches the olav-docs index using vector similarity
    to find relevant document chunks.

    Example:
        >>> tool = DocumentSearchTool()
        >>> results = await tool.search("BGP configuration on Cisco IOS")
    """

    def __init__(
        self,
        embedding_model: str = "text-embedding-3-small",
    ) -> None:
        """Initialize document search tool.

        Args:
            embedding_model: OpenAI embedding model for queries
        """
        self.embedding_service = EmbeddingService(model=embedding_model)
        self.indexer = DocumentIndexer()

    async def search(
        self,
        query: str,
        k: int = 5,
        vendor: str | None = None,
        document_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for relevant documents.

        Args:
            query: Natural language search query
            k: Number of results to return (default: 5)
            vendor: Filter by vendor (cisco, arista, juniper, etc.)
            document_type: Filter by type (manual, reference, troubleshooting, etc.)

        Returns:
            List of relevant document chunks with metadata
        """
        # Generate query embedding
        query_embedding = await self.embedding_service.embed_text(query)

        # Build filters
        filters = {}
        if vendor:
            filters["vendor"] = vendor.lower()
        if document_type:
            filters["document_type"] = document_type.lower()

        # Search
        results = await self.indexer.search_similar(
            query_embedding,
            k=k,
            filters=filters if filters else None,
        )

        logger.info(f"Document search: '{query[:50]}...' returned {len(results)} results")

        return results

    async def search_formatted(
        self,
        query: str,
        k: int = 5,
        vendor: str | None = None,
        document_type: str | None = None,
    ) -> str:
        """Search and format results as readable text.

        Args:
            query: Search query
            k: Number of results
            vendor: Vendor filter
            document_type: Document type filter

        Returns:
            Formatted string with search results
        """
        results = await self.search(query, k, vendor, document_type)

        if not results:
            return f"No documents found for: {query}"

        output_parts = [f"Found {len(results)} relevant documents:\n"]

        for i, doc in enumerate(results, 1):
            source = doc.get("source", "Unknown")
            vendor = doc.get("vendor", "unknown")
            doc_type = doc.get("document_type", "general")
            score = doc.get("_score", 0)
            content = doc.get("content", "")[:500]  # Truncate content

            output_parts.append(
                f"\n--- Result {i} (score: {score:.3f}) ---\n"
                f"Source: {source}\n"
                f"Vendor: {vendor} | Type: {doc_type}\n"
                f"Content:\n{content}...\n"
            )

        return "".join(output_parts)


# Global tool instance
_search_tool: DocumentSearchTool | None = None


def get_document_search_tool() -> DocumentSearchTool:
    """Get global DocumentSearchTool instance."""
    global _search_tool
    if _search_tool is None:
        _search_tool = DocumentSearchTool()
    return _search_tool


@tool
async def search_documents(
    query: str,
    k: int = 5,
    vendor: str | None = None,
    document_type: str | None = None,
) -> str:
    """Search vendor documentation and knowledge base.

    Use this tool to find relevant information from:
    - Vendor manuals (Cisco, Arista, Juniper, etc.)
    - Configuration guides
    - RFCs and standards
    - Troubleshooting guides

    Args:
        query: Natural language search query describing what you're looking for
        k: Number of results to return (default: 5, max: 10)
        vendor: Optional filter by vendor name (cisco, arista, juniper, etc.)
        document_type: Optional filter by document type (manual, reference, troubleshooting, configuration)

    Returns:
        Formatted search results with relevant document excerpts

    Example:
        >>> await search_documents("How to configure BGP on Cisco IOS")
        >>> await search_documents("OSPF troubleshooting", vendor="juniper")
    """
    tool = get_document_search_tool()

    # Clamp k to reasonable range
    k = max(1, min(k, 10))

    return await tool.search_formatted(
        query=query,
        k=k,
        vendor=vendor,
        document_type=document_type,
    )


@tool
async def search_vendor_docs(
    query: str,
    vendor: Literal["cisco", "arista", "juniper", "paloalto", "fortinet", "huawei", "nokia"],
    k: int = 3,
) -> str:
    """Search documentation for a specific network vendor.

    Specialized search filtered to a single vendor's documentation.
    Use when you know the vendor and need vendor-specific information.

    Args:
        query: What to search for in the vendor's documentation
        vendor: The vendor name (cisco, arista, juniper, paloalto, fortinet, huawei, nokia)
        k: Number of results (default: 3)

    Returns:
        Relevant excerpts from the vendor's documentation

    Example:
        >>> await search_vendor_docs("BGP best path selection", vendor="cisco")
        >>> await search_vendor_docs("EVPN configuration", vendor="arista")
    """
    tool = get_document_search_tool()
    return await tool.search_formatted(query=query, k=k, vendor=vendor)


@tool
async def search_rfc(
    topic: str,
    k: int = 3,
) -> str:
    """Search RFC documents and IETF standards.

    Use this to find official protocol specifications and standards.

    Args:
        topic: Protocol or standard to search for
        k: Number of results (default: 3)

    Returns:
        Relevant RFC excerpts

    Example:
        >>> await search_rfc("BGP route reflection")
        >>> await search_rfc("OSPF LSA types")
    """
    tool = get_document_search_tool()
    return await tool.search_formatted(
        query=topic,
        k=k,
        vendor="ietf",
        document_type="rfc",
    )


# Export tools for LangChain registration
DOCUMENT_TOOLS = [
    search_documents,
    search_vendor_docs,
    search_rfc,
]


def get_document_tools() -> list:
    """Get all document search tools for agent registration."""
    return DOCUMENT_TOOLS
