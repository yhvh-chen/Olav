"""Knowledge base search utilities for OLAV v0.8.

This module provides hybrid search (BM25 + vector) functionality for the knowledge base.
Separated from capabilities.py for better maintainability (per DESIGN_V0.81.md optimization).
"""

from pathlib import Path

import duckdb

from config.settings import settings


def rrf_fusion(
    fts_results: list,
    vec_results: list,
    limit: int,
    k: int = 60,
    vector_weight: float = 0.7,
    text_weight: float = 0.3,
) -> list:
    """Weighted fusion combining FTS and vector search results.

    Phase 7: Improved hybrid search with configurable weights.
    Default: 70% vector semantic relevance, 30% text keyword matching.

    Args:
        fts_results: Results from full-text search
        vec_results: Results from vector similarity search
        limit: Maximum number of results to return
        k: RRF constant (default 60)
        vector_weight: Weight for vector search (default 0.7)
        text_weight: Weight for text search (default 0.3)

    Returns:
        Combined and ranked results as list of (title, content, platform)

    Reference: https://dl.acm.org/doi/10.1145/1571941.1572114
    """
    scores = {}
    id_to_data = {}

    # Normalize weights
    total_weight = vector_weight + text_weight
    vector_weight = vector_weight / total_weight
    text_weight = text_weight / total_weight

    # Process FTS results with text weight
    for rank, row in enumerate(fts_results):
        chunk_id = row[0]
        title = row[1]
        content = row[2]
        plat = row[3] if len(row) > 3 else None

        rrf_score = 1.0 / (k + rank)
        weighted_score = rrf_score * text_weight

        scores[chunk_id] = scores.get(chunk_id, 0) + weighted_score
        id_to_data[chunk_id] = (title, content, plat)

    # Process vector results with vector weight
    for rank, row in enumerate(vec_results):
        chunk_id = row[0]
        title = row[1]
        content = row[2]
        plat = row[3] if len(row) > 3 else None

        rrf_score = 1.0 / (k + rank)
        weighted_score = rrf_score * vector_weight

        scores[chunk_id] = scores.get(chunk_id, 0) + weighted_score
        if chunk_id not in id_to_data:
            id_to_data[chunk_id] = (title, content, plat)

    # Sort by combined score and return top-k
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)[:limit]
    return [id_to_data[cid] for cid in sorted_ids]


def search_knowledge(
    query: str,
    platform: str | None,
    limit: int,
    vector_weight: float = 0.7,
    text_weight: float = 0.3,
    rerank: bool = True,
) -> str:
    """Hybrid search on knowledge base with optional reranking.

    Phase 7: Implements hybrid search + optional cross-encoder reranking:
    - BM25 text search (keyword relevance)
    - Vector semantic search (semantic similarity)
    - Weighted fusion: 70% vector, 30% BM25
    - Cross-encoder reranking for better relevance (optional)

    Args:
        query: Search query (natural language or keywords)
        platform: Optional platform filter (e.g., "cisco_ios", "huawei_vrp")
        limit: Maximum results per search method
        vector_weight: Weight for vector search (default 0.7)
        text_weight: Weight for text/BM25 search (default 0.3)
        rerank: Enable cross-encoder reranking (default True, degrades gracefully)

    Returns:
        Formatted search results with content snippets
    """
    db_path = Path(settings.agent_dir) / "data" / "knowledge.db"

    if not db_path.exists():
        return ""  # Knowledge base not initialized

    conn = duckdb.connect(str(db_path), read_only=True)

    try:
        # Split query into terms for better matching
        query_terms = query.lower().split()

        # 1. BM25-like text search (using ILIKE with term matching)
        fts_results = _execute_fts_search(conn, query_terms, query, platform, limit)

        # 2. Vector semantic search (if embeddings enabled and available)
        vec_results = _execute_vector_search(conn, query, platform, limit)

        # 3. Weighted fusion with configurable weights
        combined = rrf_fusion(
            fts_results, vec_results, limit, vector_weight=vector_weight, text_weight=text_weight
        )

        if not combined:
            return ""

        # 4. Optional cross-encoder reranking (Phase 7)
        if rerank:
            combined = _apply_reranking(query, combined, limit)

        # Format results
        return _format_results(combined, limit)

    finally:
        conn.close()


def _execute_fts_search(
    conn: duckdb.DuckDBPyConnection,
    query_terms: list[str],
    query: str,
    platform: str | None,
    limit: int,
) -> list:
    """Execute full-text search on knowledge base.

    Args:
        conn: DuckDB connection
        query_terms: Tokenized query terms
        query: Original query string
        platform: Optional platform filter
        limit: Maximum results

    Returns:
        List of (id, title, content, platform, score) tuples
    """
    # Count matching terms to approximate BM25 relevance
    fts_sql = """
        SELECT id, title, content, platform,
               SUM(CASE
                   WHEN content ILIKE ? THEN 10
                   WHEN title ILIKE ? THEN 20
                   ELSE 0
               END) as relevance_score
        FROM knowledge_chunks
        WHERE content ILIKE ? OR title ILIKE ?
    """
    # Use first term for initial matching
    first_term = query_terms[0] if query_terms else query
    params = [f"%{first_term}%", f"%{first_term}%", f"%{first_term}%", f"%{first_term}%"]

    if platform:
        fts_sql += " AND platform = ?"
        params.append(platform)

    fts_sql += " GROUP BY id, title, content, platform ORDER BY relevance_score DESC LIMIT ?"
    params.append(limit)

    return conn.execute(fts_sql, params).fetchall()


def _execute_vector_search(
    conn: duckdb.DuckDBPyConnection,
    query: str,
    platform: str | None,
    limit: int,
) -> list:
    """Execute vector similarity search on knowledge base.

    Args:
        conn: DuckDB connection
        query: Search query
        platform: Optional platform filter
        limit: Maximum results

    Returns:
        List of (id, title, content, platform, score) tuples
    """
    if settings.embedding_provider == "none":
        return []

    try:
        # Import embeddings
        if settings.embedding_provider == "ollama":
            from langchain_ollama import OllamaEmbeddings

            embeddings = OllamaEmbeddings(
                model=settings.embedding_model, base_url=settings.embedding_base_url
            )
        else:
            from langchain_openai import OpenAIEmbeddings

            embeddings = OpenAIEmbeddings(
                model=settings.embedding_model, openai_api_key=settings.embedding_api_key
            )

        query_vec = embeddings.embed_query(query)

        # Convert to string representation for SQL
        vec_str = f"[{','.join(map(str, query_vec))}]"

        vec_sql = """
            SELECT id, title, content, platform,
                   array_cosine_similarity(embedding, ?::FLOAT[768]) as score
            FROM knowledge_chunks
            WHERE embedding IS NOT NULL
        """
        vec_params = [vec_str]

        if platform:
            vec_sql += " AND platform = ?"
            vec_params.append(platform)

        vec_sql += " ORDER BY score DESC LIMIT ?"
        vec_params.append(limit)

        return conn.execute(vec_sql, vec_params).fetchall()
    except Exception:  # noqa: S110
        # Silently fall back to FTS-only if vector search fails
        return []


def _apply_reranking(query: str, combined: list, limit: int) -> list:
    """Apply cross-encoder reranking to combined results.

    Args:
        query: Search query
        combined: Combined search results
        limit: Maximum results

    Returns:
        Reranked results
    """
    try:
        from olav.tools.reranking import rerank_search_results

        return rerank_search_results(query, combined, top_k=limit)
    except Exception:  # noqa: S110
        # Reranking not available, continue with fusion results
        return combined


def _format_results(combined: list, limit: int) -> str:
    """Format search results for display.

    Args:
        combined: List of (title, content, platform[, score]) tuples
        limit: Maximum results to format

    Returns:
        Formatted markdown string
    """
    output = []
    for result in combined[:limit]:
        if len(result) == 4:
            # Reranked result with score
            title, content, plat, score = result
            score_tag = f" [Score: {score:.2f}]" if score > 0 else ""
        else:
            # Non-reranked result
            title, content, plat = result
            score_tag = ""

        content_snippet = content[:500] + "..." if len(content) > 500 else content
        platform_tag = f" ({plat})" if plat else ""
        output.append(f"### {title}{platform_tag}{score_tag}\n{content_snippet}")

    return "\n\n".join(output)
