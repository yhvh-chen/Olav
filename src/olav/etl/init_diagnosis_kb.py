# OLAV - Initialize Diagnosis Knowledge Base
"""
ETL script to create OpenSearch index for diagnosis reports.

This index stores historical diagnosis reports for Agentic RAG:
- Semantic search via embeddings
- Keyword search on fault descriptions
- Filtering by tags, protocols, layers

Usage:
    uv run python -m olav.etl.init_diagnosis_kb

    # Or via CLI:
    uv run olav --init  # Includes this initialization
"""

from __future__ import annotations

import logging

from opensearchpy import OpenSearch

from olav.core.settings import settings

logger = logging.getLogger(__name__)

DIAGNOSIS_REPORTS_INDEX = "diagnosis-reports"


def _get_opensearch_client() -> OpenSearch:
    """Get OpenSearch client using settings."""
    return OpenSearch(
        hosts=[settings.opensearch_url],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
    )


def create_diagnosis_reports_index(client: OpenSearch, force: bool = False) -> bool:
    """Create the diagnosis-reports index.

    Args:
        client: OpenSearch client
        force: If True, delete existing index and recreate

    Returns:
        True if index was created/exists, False on error
    """
    index_name = DIAGNOSIS_REPORTS_INDEX

    # Check if index exists (OpenSearch-py 2.x API)
    if client.indices.exists(index=index_name):
        if force:
            logger.info(f"Deleting existing index: {index_name}")
            client.indices.delete(index=index_name)
        else:
            logger.info(f"Index {index_name} already exists")
            return True

    # Index configuration
    index_body = {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,  # Single node setup
                # KNN settings for vector search (when embeddings are added)
                "knn": True,
                "knn.algo_param.ef_search": 100,
            },
            "analysis": {
                "analyzer": {
                    # Chinese + English analyzer
                    "text_analyzer": {
                        "type": "standard",
                        "stopwords": "_english_",
                    },
                },
            },
        },
        "mappings": {
            "properties": {
                # Identification
                "report_id": {"type": "keyword"},
                "timestamp": {"type": "date"},

                # Fault Information - searchable text
                "fault_description": {
                    "type": "text",
                    "analyzer": "text_analyzer",
                    "fields": {
                        "keyword": {"type": "keyword", "ignore_above": 512}
                    }
                },
                "source": {"type": "keyword"},
                "destination": {"type": "keyword"},
                "fault_path": {"type": "keyword"},

                # Diagnosis Results
                "root_cause": {
                    "type": "text",
                    "analyzer": "text_analyzer",
                },
                "root_cause_device": {"type": "keyword"},
                "root_cause_layer": {"type": "keyword"},
                "confidence": {"type": "float"},

                # Evidence
                "evidence_chain": {
                    "type": "text",
                    "analyzer": "text_analyzer",
                },
                "device_summaries_text": {"type": "text"},

                # Resolution
                "recommended_action": {
                    "type": "text",
                    "analyzer": "text_analyzer",
                },
                "resolution_applied": {"type": "boolean"},
                "resolution_result": {"type": "text"},

                # Metadata for filtering
                "tags": {"type": "keyword"},
                "affected_protocols": {"type": "keyword"},
                "affected_layers": {"type": "keyword"},

                # Full report (not indexed, just stored)
                "markdown_content": {
                    "type": "text",
                    "index": False,
                },

                # Vector embeddings for semantic search
                "fault_description_embedding": {
                    "type": "knn_vector",
                    "dimension": 768,  # nomic-embed-text-v1.5
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "lucene",  # Use lucene for OpenSearch 2.x
                        "parameters": {
                            "ef_construction": 256,
                            "m": 48,
                        },
                    },
                },
                "root_cause_embedding": {
                    "type": "knn_vector",
                    "dimension": 768,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "lucene",
                    },
                },
            },
        },
    }

    try:
        client.indices.create(index=index_name, body=index_body)
        logger.info(f"✅ Created index: {index_name}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to create index {index_name}: {e}")
        return False


def seed_sample_reports(client: OpenSearch) -> int:
    """Seed sample diagnosis reports for testing.

    Returns:
        Number of reports seeded
    """
    from olav.models.diagnosis_report import DiagnosisReport, DeviceSummary

    sample_reports = [
        DiagnosisReport(
            report_id="sample-001",
            fault_description="BGP peer between R1 and R2 keeps flapping",
            source="R1",
            destination="R2",
            fault_path=["R1", "R2"],
            root_cause="MTU mismatch on interconnect link causing fragmented BGP packets",
            root_cause_device="R1",
            root_cause_layer="L3",
            confidence=0.92,
            evidence_chain=[
                "BGP session up/down every 30 seconds",
                "Interface counters show high fragmentation",
                "MTU on R1 Gi0/0 is 9000, R2 Gi0/1 is 1500",
            ],
            device_summaries={
                "R1": DeviceSummary(
                    device="R1",
                    status="degraded",
                    layer_findings={"L3": ["MTU 9000 on outgoing interface"]},
                    confidence=0.9,
                ),
                "R2": DeviceSummary(
                    device="R2",
                    status="degraded",
                    layer_findings={"L3": ["MTU 1500 on incoming interface"]},
                    confidence=0.9,
                ),
            },
            recommended_action="Set consistent MTU (9000 or 1500) on both sides of the link",
            tags=["bgp", "mtu", "interface"],
            affected_protocols=["bgp"],
            affected_layers=["L3"],
        ),
        DiagnosisReport(
            report_id="sample-002",
            fault_description="Switch SW1 cannot reach SW3, intermittent packet loss",
            source="SW1",
            destination="SW3",
            fault_path=["SW1", "SW2", "SW3"],
            root_cause="STP blocked port on SW2 due to BPDU guard",
            root_cause_device="SW2",
            root_cause_layer="L2",
            confidence=0.88,
            evidence_chain=[
                "Ping from SW1 to SW3 shows 50% packet loss",
                "SW2 port Gi0/10 is in err-disabled state",
                "Logs show BPDU guard triggered",
            ],
            device_summaries={
                "SW2": DeviceSummary(
                    device="SW2",
                    status="faulty",
                    layer_findings={"L2": ["Port Gi0/10 err-disabled", "BPDU guard violation"]},
                    confidence=0.88,
                ),
            },
            recommended_action="Disable BPDU guard on trunk ports or redesign STP topology",
            tags=["stp", "bpdu", "interface"],
            affected_protocols=["stp"],
            affected_layers=["L2"],
        ),
        DiagnosisReport(
            report_id="sample-003",
            fault_description="OSPF adjacency not forming between Core-R1 and Edge-R1",
            source="Core-R1",
            destination="Edge-R1",
            fault_path=["Core-R1", "Edge-R1"],
            root_cause="OSPF area mismatch - Core-R1 in area 0, Edge-R1 in area 1",
            root_cause_device="Edge-R1",
            root_cause_layer="L3",
            confidence=0.95,
            evidence_chain=[
                "OSPF neighbor state stuck at INIT",
                "Core-R1 shows area 0.0.0.0 on interface",
                "Edge-R1 shows area 0.0.0.1 on interface",
            ],
            device_summaries={
                "Edge-R1": DeviceSummary(
                    device="Edge-R1",
                    status="faulty",
                    layer_findings={"L3": ["OSPF area misconfigured"]},
                    confidence=0.95,
                ),
            },
            recommended_action="Change Edge-R1 interface to area 0 or configure virtual-link",
            tags=["ospf", "routing", "configuration"],
            affected_protocols=["ospf"],
            affected_layers=["L3"],
        ),
    ]

    count = 0

    # Try to get embedding model for vector indexing
    embedding_model = None
    try:
        from olav.core.llm import LLMFactory
        embedding_model = LLMFactory.get_embedding_model()
        logger.info("Using embedding model for sample reports")
    except Exception as e:
        logger.warning(f"Embedding model not available, indexing without vectors: {e}")

    for report in sample_reports:
        try:
            doc = report.to_opensearch_doc()

            # Generate embeddings if model is available
            if embedding_model:
                try:
                    doc["fault_description_embedding"] = embedding_model.embed_query(
                        f"search_document: {report.fault_description}"
                    )
                    doc["root_cause_embedding"] = embedding_model.embed_query(
                        f"search_document: {report.root_cause}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to generate embedding for {report.report_id}: {e}")

            client.index(
                index=DIAGNOSIS_REPORTS_INDEX,
                id=report.report_id,
                body=doc,
            )
            count += 1
        except Exception as e:
            logger.error(f"Failed to seed report {report.report_id}: {e}")

    if count > 0:
        client.indices.refresh(index=DIAGNOSIS_REPORTS_INDEX)
        logger.info(f"✅ Seeded {count} sample diagnosis reports")

    return count


def main(force: bool = False, seed: bool = False):
    """Main initialization function.

    Args:
        force: Force recreate index (deletes existing data)
        seed: Add sample reports for testing
    """
    print("=" * 60)
    print("OLAV - Diagnosis Knowledge Base Initialization")
    print("=" * 60)

    try:
        client = _get_opensearch_client()

        # Test connection
        info = client.info()
        print(f"✅ Connected to OpenSearch {info['version']['number']}")

    except Exception as e:
        print(f"❌ Failed to connect to OpenSearch: {e}")
        print("   Make sure OpenSearch is running (docker-compose up -d opensearch)")
        return False

    # Create index
    success = create_diagnosis_reports_index(client, force=force)
    if not success:
        return False

    # Optionally seed sample data
    if seed:
        seed_sample_reports(client)

    # Verify (OpenSearch-py 2.x API)
    if client.indices.exists(index=DIAGNOSIS_REPORTS_INDEX):
        count = client.count(index=DIAGNOSIS_REPORTS_INDEX)
        print(f"✅ Index {DIAGNOSIS_REPORTS_INDEX} ready with {count['count']} documents")

    print("=" * 60)
    print("Initialization complete!")
    print("=" * 60)

    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Initialize Diagnosis Knowledge Base")
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force recreate index (WARNING: deletes existing data)"
    )
    parser.add_argument(
        "--seed", "-s",
        action="store_true",
        help="Add sample diagnosis reports for testing"
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    main(force=args.force, seed=args.seed)
