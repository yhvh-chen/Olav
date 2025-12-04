# OLAV - Knowledge Base Tools (Agentic RAG)
"""
Knowledge Base tools for diagnosis report indexing and search.

These tools enable Agentic RAG:
- kb_search: Query similar cases from knowledge base (hybrid: keyword + vector)
- kb_index_report: Index new diagnosis reports with embeddings

The knowledge base is stored in OpenSearch with:
- Full-text search on fault_description, root_cause
- Vector embeddings (nomic-embed-text) for semantic similarity
- Hybrid search combining both for best results
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.tools import tool
from opensearchpy import OpenSearch

from olav.core.settings import settings
from olav.models.diagnosis_report import DiagnosisReport, SimilarCase

logger = logging.getLogger(__name__)

# Lazy-loaded embedding model
_embedding_model: Embeddings | None = None


def _get_embedding_model() -> Embeddings:
    """Get or create embedding model (lazy loading)."""
    global _embedding_model
    if _embedding_model is None:
        from olav.core.llm import LLMFactory
        _embedding_model = LLMFactory.get_embedding_model()
        logger.info("Initialized embedding model for KB")
    return _embedding_model

# Index name for diagnosis reports
DIAGNOSIS_REPORTS_INDEX = "diagnosis-reports"


def _get_opensearch_client() -> OpenSearch:
    """Get OpenSearch client using settings."""
    return OpenSearch(
        hosts=[settings.opensearch_url],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
    )


@tool
def kb_search(
    query: str,
    size: int = 5,
    filter_tags: list[str] | None = None,
    filter_layers: list[str] | None = None,
    use_vector: bool = True,
) -> list[dict]:
    """Search knowledge base for similar diagnosis cases using hybrid search.
    
    Uses both keyword matching and vector similarity for best results:
    - Keyword search: Exact term matching on fault_description, root_cause
    - Vector search: Semantic similarity via embeddings
    
    Args:
        query: Natural language description of the fault
        size: Number of results to return (default: 5)
        filter_tags: Optional tags to filter by (e.g., ["bgp", "interface"])
        filter_layers: Optional layers to filter by (e.g., ["L2", "L3"])
        use_vector: Whether to use vector search (default: True)
    
    Returns:
        List of similar cases with:
        - case_id: Report ID
        - fault_description: What the original fault was
        - root_cause: What was identified as the cause
        - resolution: How it was fixed
        - similarity_score: How similar this case is (0-1)
        - tags: Related tags
    
    Example:
        kb_search("BGP neighbor down between R1 and R2")
        -> [
            {
                "case_id": "diag-abc123",
                "fault_description": "BGP peer not establishing",
                "root_cause": "MTU mismatch on interconnect link",
                "resolution": "Set MTU to 1500 on both sides",
                "similarity_score": 0.85,
                "tags": ["bgp", "mtu"]
            },
            ...
        ]
    """
    try:
        client = _get_opensearch_client()
        
        # Check if index exists (OpenSearch-py 2.x API)
        if not client.indices.exists(index=DIAGNOSIS_REPORTS_INDEX):
            logger.warning(f"Index {DIAGNOSIS_REPORTS_INDEX} does not exist. No historical cases available.")
            return []
        
        # Build filter clauses
        filter_clauses = []
        
        # Optional tag filter
        if filter_tags:
            filter_clauses.append({
                "terms": {"tags": filter_tags}
            })
        
        # Optional layer filter
        if filter_layers:
            filter_clauses.append({
                "terms": {"affected_layers": filter_layers}
            })
        
        # Generate query embedding for vector search
        query_embedding = None
        if use_vector:
            try:
                embedding_model = _get_embedding_model()
                # Add task prefix for nomic-embed-text (search_query:)
                query_embedding = embedding_model.embed_query(f"search_query: {query}")
                logger.debug(f"Generated query embedding with {len(query_embedding)} dimensions")
            except Exception as e:
                logger.warning(f"Failed to generate embedding, falling back to keyword-only: {e}")
                use_vector = False
        
        # Build hybrid query (keyword + vector)
        if use_vector and query_embedding:
            # Hybrid: combine BM25 text search with KNN vector search
            query_body = {
                "size": size,
                "query": {
                    "bool": {
                        "should": [
                            # Keyword search (BM25)
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": [
                                        "fault_description^3",
                                        "root_cause^2",
                                        "tags",
                                        "affected_protocols",
                                        "evidence_chain",
                                    ],
                                    "type": "best_fields",
                                    "fuzziness": "AUTO",
                                    "boost": 1.0,
                                }
                            },
                            # Vector search (KNN)
                            {
                                "knn": {
                                    "fault_description_embedding": {
                                        "vector": query_embedding,
                                        "k": size,
                                        "boost": 2.0,  # Give vector search higher weight
                                    }
                                }
                            },
                        ],
                        "filter": filter_clauses,
                        "minimum_should_match": 1,
                    }
                },
                "_source": [
                    "report_id",
                    "fault_description",
                    "root_cause",
                    "root_cause_layer",
                    "root_cause_device",
                    "recommended_action",
                    "confidence",
                    "timestamp",
                    "tags",
                    "affected_protocols",
                    "affected_layers",
                ],
                "sort": [
                    {"_score": {"order": "desc"}},
                    {"timestamp": {"order": "desc"}},
                ],
            }
        else:
            # Keyword-only fallback
            query_body = {
                "size": size,
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": [
                                        "fault_description^3",
                                        "root_cause^2",
                                        "tags",
                                        "affected_protocols",
                                        "evidence_chain",
                                    ],
                                    "type": "best_fields",
                                    "fuzziness": "AUTO",
                                }
                            }
                        ],
                        "filter": filter_clauses,
                    }
                },
                "_source": [
                    "report_id",
                    "fault_description",
                    "root_cause",
                    "root_cause_layer",
                    "root_cause_device",
                    "recommended_action",
                    "confidence",
                    "timestamp",
                    "tags",
                    "affected_protocols",
                    "affected_layers",
                ],
                "sort": [
                    {"_score": {"order": "desc"}},
                    {"timestamp": {"order": "desc"}},
                ],
            }
        
        result = client.search(
            index=DIAGNOSIS_REPORTS_INDEX,
            body=query_body,
        )
        
        cases = []
        max_score = result["hits"]["max_score"] or 1.0
        
        for hit in result["hits"]["hits"]:
            source = hit["_source"]
            # Normalize score to 0-1
            similarity = hit["_score"] / max_score if max_score > 0 else 0
            
            cases.append({
                "case_id": source.get("report_id", "unknown"),
                "fault_description": source.get("fault_description", ""),
                "root_cause": source.get("root_cause", "Unknown"),
                "root_cause_layer": source.get("root_cause_layer"),
                "root_cause_device": source.get("root_cause_device"),
                "resolution": source.get("recommended_action", "No resolution recorded"),
                "confidence": source.get("confidence", 0),
                "similarity_score": round(similarity, 2),
                "timestamp": source.get("timestamp"),
                "tags": source.get("tags", []),
                "protocols": source.get("affected_protocols", []),
                "layers": source.get("affected_layers", []),
            })
        
        search_mode = "hybrid (keyword+vector)" if use_vector and query_embedding else "keyword-only"
        logger.info(f"kb_search ({search_mode}) found {len(cases)} cases for: {query[:50]}...")
        return cases
        
    except Exception as e:
        logger.error(f"kb_search failed: {e}")
        return []


async def kb_index_report(report: DiagnosisReport) -> bool:
    """Index a diagnosis report to knowledge base with embeddings.
    
    This function adds a completed diagnosis report to the knowledge base
    for future Agentic RAG queries. Generates embeddings for semantic search.
    
    Args:
        report: DiagnosisReport to index
    
    Returns:
        True if indexing succeeded, False otherwise
    """
    try:
        client = _get_opensearch_client()
        
        # Ensure index exists (OpenSearch-py 2.x API)
        if not client.indices.exists(index=DIAGNOSIS_REPORTS_INDEX):
            logger.warning(
                f"Index {DIAGNOSIS_REPORTS_INDEX} does not exist. "
                f"Run init_diagnosis_kb.py to create it."
            )
            return False
        
        # Convert report to OpenSearch document
        doc = report.to_opensearch_doc()
        
        # Generate embeddings for semantic search
        try:
            embedding_model = _get_embedding_model()
            # Add task prefix for nomic-embed-text (search_document:)
            doc["fault_description_embedding"] = embedding_model.embed_query(
                f"search_document: {report.fault_description}"
            )
            doc["root_cause_embedding"] = embedding_model.embed_query(
                f"search_document: {report.root_cause}"
            )
            logger.debug(f"Generated embeddings for report {report.report_id}")
        except Exception as e:
            logger.warning(f"Failed to generate embeddings, indexing without vectors: {e}")
            # Continue without embeddings - keyword search will still work
        
        # Index document
        result = client.index(
            index=DIAGNOSIS_REPORTS_INDEX,
            id=report.report_id,
            body=doc,
            refresh=True,  # Make immediately searchable
        )
        
        logger.info(f"Indexed diagnosis report {report.report_id} to knowledge base")
        return result.get("result") in ("created", "updated")
        
    except Exception as e:
        logger.error(f"Failed to index report {report.report_id}: {e}")
        return False


def kb_get_report(report_id: str) -> DiagnosisReport | None:
    """Retrieve a specific report from knowledge base.
    
    Args:
        report_id: Report ID to retrieve
    
    Returns:
        DiagnosisReport if found, None otherwise
    """
    try:
        client = _get_opensearch_client()
        
        if not client.indices.exists(index=DIAGNOSIS_REPORTS_INDEX):
            return None
        
        result = client.get(
            index=DIAGNOSIS_REPORTS_INDEX,
            id=report_id,
        )
        
        if result.get("found"):
            return DiagnosisReport(**result["_source"])
        return None
        
    except Exception as e:
        logger.error(f"Failed to get report {report_id}: {e}")
        return None


def kb_delete_report(report_id: str) -> bool:
    """Delete a report from knowledge base.
    
    Args:
        report_id: Report ID to delete
    
    Returns:
        True if deleted, False otherwise
    """
    try:
        client = _get_opensearch_client()
        
        if not client.indices.exists(index=DIAGNOSIS_REPORTS_INDEX):
            return False
        
        result = client.delete(
            index=DIAGNOSIS_REPORTS_INDEX,
            id=report_id,
            refresh=True,
        )
        
        return result.get("result") == "deleted"
        
    except Exception as e:
        logger.error(f"Failed to delete report {report_id}: {e}")
        return False


def kb_stats() -> dict[str, Any]:
    """Get knowledge base statistics.
    
    Returns:
        Dict with stats like total_reports, recent_reports, etc.
    """
    try:
        client = _get_opensearch_client()
        
        if not client.indices.exists(index=DIAGNOSIS_REPORTS_INDEX):
            return {"status": "not_initialized", "total_reports": 0}
        
        # Count total documents
        count_result = client.count(index=DIAGNOSIS_REPORTS_INDEX)
        total = count_result.get("count", 0)
        
        # Get index stats
        stats = client.indices.stats(index=DIAGNOSIS_REPORTS_INDEX)
        index_stats = stats.get("indices", {}).get(DIAGNOSIS_REPORTS_INDEX, {})
        
        return {
            "status": "ready",
            "total_reports": total,
            "index_size_bytes": index_stats.get("total", {}).get("store", {}).get("size_in_bytes", 0),
        }
        
    except Exception as e:
        logger.error(f"Failed to get kb stats: {e}")
        return {"status": "error", "error": str(e)}


__all__ = [
    "kb_search",
    "kb_index_report",
    "kb_get_report",
    "kb_delete_report",
    "kb_stats",
    "DIAGNOSIS_REPORTS_INDEX",
]
