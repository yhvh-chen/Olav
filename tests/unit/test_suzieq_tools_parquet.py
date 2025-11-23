import os
import asyncio
import pandas as pd
import pytest
from pathlib import Path

from olav.tools.suzieq_parquet_tool import suzieq_schema_search, suzieq_query, SUZIEQ_SCHEMA

PARQUET_BASE = Path("data/suzieq-parquet")

@pytest.fixture(scope="module", autouse=True)
def setup_parquet(tmp_path_factory):
    """Create minimal parquet data for bgp table to exercise queries."""
    # Ensure directory structure
    table_dir = PARQUET_BASE / "bgp" / "sqvers=v1" / "namespace=lab" / "hostname=r1"
    table_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([
        {
            "namespace": "lab",
            "hostname": "r1",
            "vrf": "default",
            "peer": "192.0.2.1",
            "asn": 65001,
            "peerAsn": 65002,
            "state": "Established",
            "peerHostname": "r2",
        },
        {
            "namespace": "lab",
            "hostname": "r1",
            "vrf": "default",
            "peer": "198.51.100.2",
            "asn": 65001,
            "peerAsn": 65003,
            "state": "Idle",
            "peerHostname": "r3",
        },
    ])
    df.to_parquet(table_dir / "data.parquet")
    yield

@pytest.mark.asyncio
async def test_schema_search_basic():
    result = await suzieq_schema_search.ainvoke({"query": "bgp peers"})
    assert "bgp" in result["tables"]
    assert "fields" in result["bgp"]
    assert set(SUZIEQ_SCHEMA["bgp"]["fields"]) == set(result["bgp"]["fields"])
    assert "methods" in result["bgp"] and result["bgp"]["methods"] == ["get", "summarize"]

@pytest.mark.asyncio
async def test_query_get():
    result = await suzieq_query.ainvoke({"table": "bgp", "method": "get"})
    assert result.get("error") is None
    assert result["table"] == "bgp"
    assert result["count"] >= 2
    assert any(row["state"] == "Established" for row in result["data"])  # record content check
    # assert "__meta__" in result and "elapsed_sec" in result["__meta__"]

@pytest.mark.asyncio
async def test_query_summarize():
    result = await suzieq_query.ainvoke({"table": "bgp", "method": "summarize"})
    assert result.get("error") is None
    summary = result["data"][0]
    assert "total_records" in summary and summary["total_records"] >= 2
    assert "state_counts" in summary

@pytest.mark.asyncio
async def test_query_unknown_table():
    result = await suzieq_query.ainvoke({"table": "notatable", "method": "get"})
    assert result.get("error") is not None
    assert "available_tables" in result
