"""ETL pipelines for schema and data initialization.

This package provides ETL scripts for Schema indices:

Schema Indices (source-of-truth for schema discovery):
- netbox_schema_etl: NetBox OpenAPI → netbox-schema, netbox-schema-fields
- suzieq_schema_etl: SuzieQ Avro schemas → suzieq-schema, suzieq-schema-fields
- init_schema: OpenConfig YANG → openconfig-schema

LLM-Driven Sync:
- Field mappings are now handled by LLMDiffEngine (no ETL required)
- See olav.sync.llm_diff for the new approach

Infrastructure:
- init_postgres: PostgreSQL checkpointer tables for LangGraph

Usage:
    # Run individual ETL
    uv run python -m olav.etl.netbox_schema_etl
    uv run python -m olav.etl.suzieq_schema_etl

    # Or import and run programmatically
    from olav.etl import netbox_schema_etl, suzieq_schema_etl

    netbox_schema_etl.main(force=True)
    suzieq_schema_etl.main(force=True)
"""

from olav.etl import netbox_schema_etl, suzieq_schema_etl

__all__ = [
    "netbox_schema_etl",
    "suzieq_schema_etl",
]