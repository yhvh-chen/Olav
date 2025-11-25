"""Initialize olav-episodic-memory index for historical success tracking."""

import logging
from datetime import UTC, datetime

from opensearchpy import OpenSearch

from olav.core.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """Create olav-episodic-memory index to store historical intent→XPath success patterns.

    Index Schema:
        - intent (text): User intent in natural language (e.g., "查询 BGP 状态")
        - xpath (keyword): OpenConfig XPath or SuzieQ query used
        - tool_used (keyword): Tool name that executed successfully (suzieq_query, netconf_execute, etc.)
        - device_type (keyword): Device type or hostname
        - success (boolean): Whether execution succeeded
        - timestamp (date): When execution occurred
        - execution_time_ms (long): How long execution took
        - parameters (object): Tool parameters used (stored as JSON)
        - result_summary (text): Brief summary of result

    Process:
        1. Connect to OpenSearch
        2. Create index with mapping
        3. Insert sample historical data for testing
    """
    logger.info("Initializing olav-episodic-memory index...")

    client = OpenSearch(
        hosts=[settings.opensearch_url],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
    )

    index_name = "olav-episodic-memory"

    # Delete existing index if present
    if client.indices.exists(index=index_name):
        logger.info(f"Index {index_name} exists. Deleting for fresh start...")
        client.indices.delete(index=index_name)

    # Create index mapping optimized for semantic search and filtering
    mapping = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    "intent_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding"],
                    }
                }
            },
        },
        "mappings": {
            "properties": {
                "intent": {
                    "type": "text",
                    "analyzer": "intent_analyzer",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "xpath": {"type": "keyword"},
                "tool_used": {"type": "keyword"},
                "device_type": {"type": "keyword"},
                "success": {"type": "boolean"},
                "timestamp": {"type": "date"},
                "execution_time_ms": {"type": "long"},
                "parameters": {"type": "object", "enabled": True},
                "result_summary": {"type": "text"},
                "strategy_used": {"type": "keyword"},
            },
        },
    }

    client.indices.create(index=index_name, body=mapping)
    logger.info(f"✓ Created index: {index_name}")

    # Insert sample historical data for RAG testing
    sample_memories = [
        {
            "intent": "查询 R1 BGP 状态",
            "xpath": "table=bgp, hostname=R1",
            "tool_used": "suzieq_query",
            "device_type": "router",
            "success": True,
            "timestamp": datetime.now(UTC).isoformat(),
            "execution_time_ms": 234,
            "parameters": {"table": "bgp", "hostname": "R1", "method": "get"},
            "result_summary": "Found 2 BGP neighbors in Established state",
            "strategy_used": "fast_path",
        },
        {
            "intent": "查询所有接口状态",
            "xpath": "table=interfaces, method=summarize",
            "tool_used": "suzieq_query",
            "device_type": "router",
            "success": True,
            "timestamp": datetime.now(UTC).isoformat(),
            "execution_time_ms": 456,
            "parameters": {"table": "interfaces", "method": "summarize"},
            "result_summary": "Total 24 interfaces, 20 up, 4 down",
            "strategy_used": "fast_path",
        },
        {
            "intent": "配置 BGP neighbor 192.168.1.1",
            "xpath": "/network-instances/network-instance/protocols/protocol/bgp/neighbors/neighbor[neighbor-address=192.168.1.1]/config",
            "tool_used": "netconf_execute",
            "device_type": "juniper",
            "success": True,
            "timestamp": datetime.now(UTC).isoformat(),
            "execution_time_ms": 1823,
            "parameters": {
                "operation": "edit-config",
                "xpath": "/network-instances/network-instance/protocols/protocol/bgp/neighbors/neighbor",
                "config": {"neighbor-address": "192.168.1.1", "peer-as": 65001},
            },
            "result_summary": "BGP neighbor configured successfully",
            "strategy_used": "fast_path",
        },
        {
            "intent": "检查 OSPF 邻居状态",
            "xpath": "table=ospf, method=get",
            "tool_used": "suzieq_query",
            "device_type": "router",
            "success": True,
            "timestamp": datetime.now(UTC).isoformat(),
            "execution_time_ms": 312,
            "parameters": {"table": "ospf", "method": "get"},
            "result_summary": "3 OSPF neighbors in Full state",
            "strategy_used": "fast_path",
        },
        {
            "intent": "批量检查所有路由器 BGP 状态",
            "xpath": "table=bgp, method=summarize",
            "tool_used": "suzieq_query",
            "device_type": "router",
            "success": True,
            "timestamp": datetime.now(UTC).isoformat(),
            "execution_time_ms": 892,
            "parameters": {"table": "bgp", "method": "summarize"},
            "result_summary": "Checked 15 routers, 142 BGP sessions total",
            "strategy_used": "batch_path",
        },
        {
            "intent": "查看 R2 接口描述",
            "xpath": "table=interfaces, hostname=R2, columns=hostname,ifname,description",
            "tool_used": "suzieq_query",
            "device_type": "router",
            "success": True,
            "timestamp": datetime.now(UTC).isoformat(),
            "execution_time_ms": 178,
            "parameters": {
                "table": "interfaces",
                "hostname": "R2",
                "columns": ["hostname", "ifname", "description"],
                "method": "get",
            },
            "result_summary": "Retrieved 8 interfaces with descriptions",
            "strategy_used": "fast_path",
        },
    ]

    # Bulk index sample data
    for doc in sample_memories:
        client.index(index=index_name, body=doc)

    logger.info(f"✓ Indexed {len(sample_memories)} sample episodic memories")
    logger.info("  Sample intents:")
    for doc in sample_memories[:3]:
        logger.info(f"    - {doc['intent']} → {doc['tool_used']}")

    logger.info("✓ Episodic memory initialization complete")


if __name__ == "__main__":
    main()
