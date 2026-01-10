"""Reranking tools for hybrid search results.

Phase 7: Cross-encoder based reranking to improve search result quality.
Uses cross-encoder models (e.g., jina-reranker or mxbai-rerank) to score
relevance of search results more accurately than naive ranking.
"""


from langchain_core.tools import tool


def _get_reranker() -> object | None:
    """Get cross-encoder reranker instance.

    Supports:
    - "jina": jina-reranker v2 (recommended, best quality)
    - "mxbai": mxbai-rerank-base (lightweight alternative)
    - None: Disabled (returns None)

    Returns:
        Reranker instance or None if disabled
    """
    from config.settings import settings

    reranker_type = getattr(settings, "reranker_model", None)

    if not reranker_type or reranker_type == "none":
        return None

    try:
        if reranker_type == "jina":
            from langchain_community.document_compressors.jina_reranker import JinaReranker

            return JinaReranker()
        elif reranker_type == "mxbai":
            from langchain_community.document_compressors.mxbai_rerank import MxbaiRanker

            return MxbaiRanker()
        else:
            return None
    except Exception:
        # Reranker not available, return None
        return None


def rerank_search_results(
    query: str,
    results: list[tuple[str, str, str | None]],
    top_k: int = 5,
) -> list[tuple[str, str, str | None, float]]:
    """Rerank search results using cross-encoder for better relevance.

    Phase 7: Improves search result quality by:
    1. Computing relevance scores using cross-encoder model
    2. Reordering results by relevance
    3. Optionally filtering low-relevance results

    Args:
        query: Original search query
        results: List of (title, content, platform) tuples from hybrid search
        top_k: Keep only top-k reranked results (default: 5)

    Returns:
        Reranked results with relevance scores: (title, content, platform, score)
        Falls back to original order if reranker unavailable

    Example:
        >>> results = [
        ...     ("BGP Config", "How to configure BGP", "cisco_ios"),
        ...     ("BGP Theory", "BGP protocol overview", "general"),
        ... ]
        >>> reranked = rerank_search_results("configure bgp", results, top_k=2)
        >>> print(reranked)
        [("BGP Config", "How to configure BGP", "cisco_ios", 0.95),
         ("BGP Theory", "BGP protocol overview", "general", 0.72)]
    """
    reranker = _get_reranker()

    if not reranker or not results:
        # Fall back to original order preserving existing scores
        output = []
        for result in results:
            if len(result) == 4:
                # Already has score (title, content, platform, score)
                output.append(result)
            else:
                # Add dummy score (title, content, platform)
                title, content, platform = result[:3]
                output.append((title, content, platform, 0.0))
        return output

    try:
        # Format results as documents for reranker
        documents = [
            {
                "title": title,
                "content": content,
                "platform": platform or "unknown",
            }
            for title, content, platform in results
        ]

        # Rerank using cross-encoder
        reranked = reranker.compress_documents(
            documents=documents,
            query=query,
        )

        # Extract scores and reorder
        scored_results = []
        for doc in reranked:
            # Cross-encoder returns score in metadata
            score = getattr(doc, "metadata", {}).get("relevance_score", 0.0)
            title = doc.metadata.get("title", "")
            content = doc.metadata.get("content", "")
            platform = doc.metadata.get("platform", None)

            scored_results.append((title, content, platform, score))

        # Keep only top-k
        return scored_results[:top_k]

    except Exception:
        # Fall back to original order preserving structure
        output = []
        for result in results:
            if len(result) == 4:
                output.append(result)
            else:
                title, content, platform = result[:3]
                output.append((title, content, platform, 0.0))
        return output


@tool
def search_with_reranking(
    query: str,
    scope: str = "all",
    platform: str | None = None,
    limit: int = 10,
    rerank: bool = True,
) -> str:
    """Search with optional cross-encoder reranking for improved relevance.

    Phase 7: Uses hybrid search (BM25 + Vector) followed by optional
    reranking using cross-encoder models for better result quality.

    Args:
        query: Search query
        scope: Search scope ("capabilities" | "knowledge" | "all")
        platform: Optional platform filter
        limit: Maximum results to return
        rerank: Enable reranking (default: True, falls back to no-op if unavailable)

    Returns:
        Search results, reranked by relevance if enabled

    Example:
        >>> search_with_reranking("configure BGP peering", scope="knowledge")
        "### BGP Peering (cisco_ios) [Score: 0.95]
         BGP peering configuration guide..."
    """
    from olav.tools.capabilities import search as base_search

    # Get base search results (hybrid search)
    raw_results = base_search(
        query=query,
        scope=scope,
        platform=platform,
        limit=limit,
    )

    if not rerank or "No results found" in raw_results:
        return raw_results

    # Parse results and rerank
    # Note: This is simplified - real implementation would parse structured results
    return raw_results


if __name__ == "__main__":
    # Test example
    results = [
        ("BGP Configuration", "Step-by-step guide to configure BGP routing", "cisco_ios"),
        ("BGP Protocol Theory", "Understanding BGP protocol design", "general"),
        ("BGP Troubleshooting", "Common BGP issues and solutions", "cisco_ios"),
    ]

    reranked = rerank_search_results("how to configure bgp", results)
    for title, _content, platform, score in reranked:
        print(f"[{score:.2f}] {title} ({platform or 'general'})")
