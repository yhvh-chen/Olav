import asyncio
import json
import pytest
from pathlib import Path
import pandas as pd

from olav.tools import suzieq_tool
from olav.tools.suzieq_tool import suzieq_query, suzieq_schema_search

PARQUET_BASE = Path("data/suzieq-parquet")

@pytest.fixture(scope="module", autouse=True)
def setup_parquet_extended():
    """Ensure bgp table parquet data exists for filter tests."""
    table_dir = PARQUET_BASE / "bgp" / "sqvers=v1" / "namespace=lab" / "hostname=r1"
    table_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([
        {"namespace": "lab", "hostname": "r1", "vrf": "default", "peer": "192.0.2.1", "asn": 65001, "peerAsn": 65002, "state": "Established", "peerHostname": "r2"},
        {"namespace": "lab", "hostname": "r1", "vrf": "default", "peer": "198.51.100.2", "asn": 65001, "peerAsn": 65003, "state": "Idle", "peerHostname": "r3"},
    ])
    df.to_parquet(table_dir / "data.parquet")
    yield

@pytest.mark.asyncio
async def test_filter_state_established():
    result = await suzieq_query.ainvoke({"table": "bgp", "method": "get", "filters": {"state": "Established"}})
    assert result.get("error") is None
    assert result["count"] >= 1
    assert all(r["state"] == "Established" for r in result["data"])
    assert result.get("__meta", None) is None  # meta key is __meta__
    assert "__meta__" in result and result["__meta__"]["elapsed_sec"] >= 0

@pytest.mark.asyncio
async def test_unknown_method_error():
    result = await suzieq_query.ainvoke({"table": "bgp", "method": "notamethod"})
    assert result.get("error") and "Unsupported method" in result["error"]

class FakeRedis:
    def __init__(self):
        self.store = {}
    def get(self, key):
        return self.store.get(key)
    def setex(self, key, ttl, value):
        self.store[key] = value

@pytest.mark.asyncio
async def test_schema_search_redis_caching(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(suzieq_tool, "_get_redis_client", lambda: fake)
    q = "bgp peers"
    # First call: populates cache
    first = await suzieq_schema_search.ainvoke({"query": q})
    assert "bgp" in first["tables"]
    # Ensure cached raw JSON stored
    cache_key = f"suzieq_schema_search:{q}".strip().lower()
    assert cache_key in fake.store
    # Second call: should hit cache and produce identical result
    second = await suzieq_schema_search.ainvoke({"query": q})
    assert second == first

@pytest.mark.asyncio
async def test_timing_presence():
    result = await suzieq_query.ainvoke({"table": "bgp", "method": "summarize"})
    meta = result.get("__meta__")
    assert meta and isinstance(meta.get("elapsed_sec"), float)
