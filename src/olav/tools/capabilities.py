"""Capabilities tools for OLAV v0.8.

This module provides tools for searching capabilities (CLI commands and API endpoints),
searching knowledge base (vendor docs, wiki, learned solutions),
and making API calls to external systems.

Phase 4: Knowledge Base Integration - Unified search with hybrid FTS + vector retrieval.
Phase 7: Hybrid Search - BM25 + Vector with weighted fusion (default: 0.7 vector, 0.3 BM25).
"""

from pathlib import Path
from typing import Any, Literal

import duckdb
import httpx
from langchain_core.tools import tool

from config.settings import settings
from olav.core.database import get_database


@tool
def search_capabilities(
    query: str,
    type: Literal["command", "api", "all"] = "all",
    platform: str | None = None,
    limit: int = 20,
) -> str:
    """Search available CLI commands or API endpoints.

    This tool searches the capability database for matching CLI commands or API endpoints.
    Use this to discover what commands are available before executing them.

    Args:
        query: Search keyword (e.g., "interface", "bgp", "device", "route")
        type: Capability type to search
            - "command": Only CLI commands
            - "api": Only API endpoints
            - "all": Search both (default)
        platform: Filter by platform (e.g., "cisco_ios", "huawei_vrp", "netbox", "zabbix")
        limit: Maximum number of results to return (default: 20)

    Returns:
        List of matching capabilities with names, descriptions, and write status

    Examples:
        >>> search_capabilities("interface", type="command", platform="cisco_ios")
        "Found 3 capabilities:
        1. show interface* (cisco_ios) - Read-only
        2. show ip interface brief (cisco_ios) - Read-only
        3. configure terminal (cisco_ios) - **REQUIRES APPROVAL**"

        >>> search_capabilities("device", type="api", platform="netbox")
        "Found 2 capabilities:
        1. GET /dcim/devices/ (netbox) - Query device list
        2. PATCH /dcim/devices/{id}/ (netbox) - **REQUIRES APPROVAL**"
    """
    db = get_database()

    results = db.search_capabilities(
        query=query,
        cap_type=type,
        platform=platform,
        limit=limit,
    )

    if not results:
        return f"No capabilities found matching '{query}'"

    output = [f"Found {len(results)} capabilities:"]

    for i, cap in enumerate(results, 1):
        cap_type = cap["type"]
        cap_platform = cap["platform"]
        name = cap["name"]
        method = cap.get("method", "")
        description = cap.get("description", "")
        is_write = cap["is_write"]

        if cap_type == "api":
            # API endpoint
            line = f"{i}. {method} {name} ({cap_platform})"
            if description:
                line += f" - {description}"
            if is_write:
                line += " - **REQUIRES APPROVAL**"
        else:
            # CLI command
            line = f"{i}. {name} ({cap_platform})"
            if description:
                line += f" - {description}"
            if is_write:
                line += " - **REQUIRES APPROVAL**"

        output.append(line)

    return "\n".join(output)


@tool
def api_call(
    system: str,
    method: str,
    endpoint: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> str:
    """Make an API call to an external system.

    This tool makes HTTP requests to external API systems like NetBox or Zabbix.
    Use search_capabilities() first to discover available endpoints.

    Args:
        system: API system name (e.g., "netbox", "zabbix")
        method: HTTP method (GET, POST, PUT, PATCH, DELETE)
        endpoint: API endpoint path (e.g., "/dcim/devices/")
        params: URL query parameters (for GET requests)
        body: Request body (for POST, PUT, PATCH requests)

    Returns:
        API response data or error message

    Examples:
        >>> api_call("netbox", "GET", "/dcim/devices/", params={"name": "R1"})
        '{"count": 1, "results": [{"id": 1, "name": "R1", ...}]}'

        >>> api_call("netbox", "PATCH", "/dcim/devices/1/", body={"status": "active"})
        '{"id": 1, "name": "R1", "status": "active", ...}'

    Security:
        Write operations (POST, PUT, PATCH, DELETE) require HITL approval.
        API credentials are loaded from environment variables.
    """
    import os

    # Load API credentials from environment
    # Expected format: {SYSTEM}_URL, {SYSTEM}_TOKEN or {SYSTEM}_USER/PASSWORD
    url_var = f"{system.upper()}_URL"
    token_var = f"{system.upper()}_TOKEN"
    user_var = f"{system.upper()}_USER"
    password_var = f"{system.upper()}_PASSWORD"

    base_url = os.getenv(url_var)
    if not base_url:
        return f"Error: {url_var} environment variable not set"

    # Build full URL
    url = f"{base_url.rstrip('/')}{endpoint}"

    # Prepare headers
    headers = {"Content-Type": "application/json"}

    # Try token auth first
    token = os.getenv(token_var)
    if token:
        headers["Authorization"] = f"Token {token}"

    # Try basic auth
    username = os.getenv(user_var)
    password = os.getenv(password_var)
    if username and password and not token:
        # Use basic auth
        pass

    try:
        with httpx.Client() as client:
            if username and password and not token:
                # Basic auth
                if method.upper() == "GET":
                    response = client.get(
                        url,
                        params=params,
                        headers=headers,
                        auth=(username, password),
                        timeout=30.0,
                    )
                elif method.upper() == "POST":
                    response = client.post(
                        url,
                        params=params,
                        json=body,
                        headers=headers,
                        auth=(username, password),
                        timeout=30.0,
                    )
                elif method.upper() == "PUT":
                    response = client.put(
                        url,
                        params=params,
                        json=body,
                        headers=headers,
                        auth=(username, password),
                        timeout=30.0,
                    )
                elif method.upper() == "PATCH":
                    response = client.patch(
                        url,
                        params=params,
                        json=body,
                        headers=headers,
                        auth=(username, password),
                        timeout=30.0,
                    )
                elif method.upper() == "DELETE":
                    response = client.delete(
                        url,
                        params=params,
                        headers=headers,
                        auth=(username, password),
                        timeout=30.0,
                    )
                else:
                    return f"Error: Unsupported HTTP method: {method}"
            else:
                # Token auth or no auth
                if method.upper() == "GET":
                    response = client.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=30.0,
                    )
                elif method.upper() == "POST":
                    response = client.post(
                        url,
                        params=params,
                        json=body,
                        headers=headers,
                        timeout=30.0,
                    )
                elif method.upper() == "PUT":
                    response = client.put(
                        url,
                        params=params,
                        json=body,
                        headers=headers,
                        timeout=30.0,
                    )
                elif method.upper() == "PATCH":
                    response = client.patch(
                        url,
                        params=params,
                        json=body,
                        headers=headers,
                        timeout=30.0,
                    )
                elif method.upper() == "DELETE":
                    response = client.delete(
                        url,
                        params=params,
                        headers=headers,
                        timeout=30.0,
                    )
                else:
                    return f"Error: Unsupported HTTP method: {method}"

            # Check for HTTP errors
            response.raise_for_status()

            # Return JSON response
            return response.text

    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code} - {e.response.text}"

    except httpx.RequestError as e:
        return f"Error: Request failed - {e}"

    except Exception as e:
        return f"Error: {e}"


# =============================================================================
# Knowledge Base Search (Phase 4: Knowledge Base Integration)
# =============================================================================


def _rrf_fusion(
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


def _search_knowledge(
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

        limit: Maximum results per search method
        vector_weight: Weight for vector search (default 0.7)
        text_weight: Weight for text/BM25 search (default 0.3)

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

        fts_results = conn.execute(fts_sql, params).fetchall()

        # 2. Vector semantic search (if embeddings enabled and available)
        vec_results = []
        if settings.embedding_provider != "none":
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

                vec_results = conn.execute(vec_sql, vec_params).fetchall()
            except Exception:  # noqa: S110
                # Silently fall back to FTS-only if vector search fails
                pass

        # 3. Weighted fusion with configurable weights
        combined = _rrf_fusion(
            fts_results, vec_results, limit, vector_weight=vector_weight, text_weight=text_weight
        )

        if not combined:
            return ""

        # 4. Optional cross-encoder reranking (Phase 7)
        if rerank:
            try:
                from olav.tools.reranking import rerank_search_results

                combined = rerank_search_results(query, combined, top_k=limit)
            except Exception:  # noqa: S110
                # Reranking not available, continue with fusion results
                pass

        # Format results
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

    finally:
        conn.close()


@tool
def search(
    query: str,
    scope: Literal["capabilities", "knowledge", "all"] = "all",
    platform: str | None = None,
    limit: int = 10,
) -> str:
    """Unified search for CLI commands, API endpoints, and documentation.

    This is the primary search tool combining:
    - Capabilities: CLI commands and API endpoints
    - Knowledge: Vendor docs, user wiki, runbooks, and learned solutions

    Args:
        query: Search query (command name, error code, or natural language)
        scope: What to search ("capabilities" | "knowledge" | "all")
        platform: Filter by platform (e.g., "cisco_ios", "huawei_vrp")
        limit: Maximum results per scope (default: 10)

    Returns:
        Combined search results with source attribution

    Examples:
        >>> search("interface status", scope="all")
        "## CLI Commands & APIs
        Found 5 capabilities:
        ...

        ---
        ## Documentation
        ### Interface Troubleshooting
        To check interface status...
        ..."

        >>> search("BGP error", scope="knowledge", platform="cisco_ios")
        "## Documentation
        ### BGP Troubleshooting Guide (cisco_ios)
        Common BGP errors include...
        ..."
    """
    results = []

    # Search capabilities
    if scope in ("capabilities", "all"):
        cap_results = search_capabilities(
            query=query,
            type="all",
            platform=platform,
            limit=limit,
        )
        if "No capabilities found" not in cap_results:
            results.append("## CLI Commands & APIs\n" + cap_results)

    # Search knowledge base
    if scope in ("knowledge", "all"):
        know_results = _search_knowledge(query, platform, limit)
        if know_results:
            results.append("## Documentation\n" + know_results)

    if not results:
        return f"No results found for: {query}"

    return "\n\n---\n\n".join(results)
