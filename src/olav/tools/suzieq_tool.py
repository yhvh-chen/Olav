"""Parquet-based SuzieQ tools with Redis-cached schema search.

This module replaces the earlier broken hybrid implementation. It provides two
LangChain tools:
    1. suzieq_schema_search - discover tables and fields
    2. suzieq_query          - read & summarize Parquet data

Advanced analytical methods (top, lpm, describe, etc.) are intentionally
omitted in Parquet mode for simplicity. Only 'get' and 'summarize' are
supported.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Literal

import pandas as pd
import redis
from langchain_core.tools import tool

from olav.core.settings import settings

logger = logging.getLogger(__name__)

SUZIEQ_SCHEMA: dict[str, dict[str, Any]] = {
    "bgp": {
        "fields": ["namespace", "hostname", "vrf", "peer", "asn", "peerAsn", "state", "peerHostname"],
        "description": "BGP protocol information",
    },
    "interfaces": {
        "fields": ["namespace", "hostname", "ifname", "state", "adminState", "type", "mtu", "speed"],
        "description": "Network interface status and configuration",
    },
    "routes": {
        "fields": ["namespace", "hostname", "vrf", "prefix", "nexthopIp", "protocol", "metric"],
        "description": "Routing table entries",
    },
    "lldp": {
        "fields": ["namespace", "hostname", "ifname", "peerHostname", "peerIfname"],
        "description": "LLDP neighbor discovery",
    },
    "macs": {
        "fields": ["namespace", "hostname", "vlan", "macaddr", "oif", "remoteVtepIp"],
        "description": "MAC address table",
    },
    "device": {
        "fields": ["namespace", "hostname", "model", "vendor", "version", "architecture", "status"],
        "description": "Device hardware/software info",
    },
}

def _get_redis_client() -> redis.Redis | None:
    url = getattr(settings, "redis_url", None) or os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        return redis.from_url(url, decode_responses=True)
    except Exception as e:  # pragma: no cover - best effort
        logger.warning(f"Redis unavailable: {e}")
        return None


def _get_parquet_dir() -> str:
    return os.getenv("SUZIEQ_PARQUET_DIR", "data/suzieq-parquet")


@tool
async def suzieq_schema_search(query: str) -> dict[str, Any]:
    """Discover available SuzieQ tables and their fields.

    Args:
        query: Natural language keywords (e.g. "bgp peers", "interfaces", "routes")
    Returns:
        Mapping containing matching tables and their metadata.
    """
    cache_key = f"suzieq_schema_search:{query.strip().lower()}"
    rds = _get_redis_client()
    if rds:
        cached = rds.get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

    keywords = query.lower().split()
    matches = [
        t for t, meta in SUZIEQ_SCHEMA.items()
        if any(k in t.lower() or k in meta["description"].lower() for k in keywords)
    ]
    if not matches:
        matches = list(SUZIEQ_SCHEMA.keys())[:5]

    result: dict[str, Any] = {"tables": matches}
    for t in matches:
        result[t] = {
            "fields": SUZIEQ_SCHEMA[t]["fields"],
            "description": SUZIEQ_SCHEMA[t]["description"],
            "methods": ["get", "summarize"],
        }

    if rds:
        try:
            rds.setex(cache_key, 600, json.dumps(result, ensure_ascii=False))
        except Exception as e:  # pragma: no cover - cache failure is non-fatal
            logger.warning(f"Redis cache set failed: {e}")
    return result


@tool
async def suzieq_query(
    table: str,
    method: str = "get",
    filters: dict[str, Any] | None = None,
    **extra_filters: Any,
) -> dict[str, Any]:
    """Query SuzieQ Parquet data.

    Supported methods:
        - get: return raw rows (truncated to 100)
        - summarize: basic counts by common columns
    """
    start = time.perf_counter()
    if table not in SUZIEQ_SCHEMA:
        return {
            "error": f"Unknown table '{table}'. Use suzieq_schema_search first.",
            "available_tables": list(SUZIEQ_SCHEMA.keys()),
        }

    if method not in {"get", "summarize"}:
        return {"error": f"Unsupported method '{method}'", "table": table, "allowed_methods": ["get", "summarize"]}

    parquet_dir = _get_parquet_dir()
    table_dir = os.path.join(parquet_dir, table)
    if not os.path.exists(table_dir):
        return {
            "error": f"No data directory for table '{table}'",
            "expected_path": table_dir,
            "table": table,
        }
    try:
        import glob
        files = glob.glob(os.path.join(table_dir, "**", "*.parquet"), recursive=True)
        if not files:
            return {
                "error": f"No parquet files found for table '{table}'",
                "table": table,
                "path": table_dir,
            }
        dfs = [pd.read_parquet(f) for f in files]
        df = pd.concat(dfs, ignore_index=True)
        # Merge filters (explicit dict plus any extra keyword filters)
        all_filters: dict[str, Any] = {}
        if filters:
            all_filters.update(filters)
        if extra_filters:
            all_filters.update(extra_filters)
        for field, value in all_filters.items():
            if field in df.columns:
                df = df[df[field] == value]
        if method == "get":
            data = df.head(100).to_dict(orient="records")
            payload = {
                "data": data,
                "count": len(df),
                "columns": list(df.columns),
                "table": table,
                "truncated": len(df) > 100,
            }
        elif method == "summarize":
            summary: dict[str, Any] = {}
            if "state" in df.columns:
                summary["state_counts"] = df["state"].value_counts().to_dict()
            if "adminState" in df.columns:
                summary["admin_state_counts"] = df["adminState"].value_counts().to_dict()
            if "type" in df.columns:
                summary["type_counts"] = df["type"].value_counts().to_dict()
            summary["total_records"] = len(df)
            if "hostname" in df.columns:
                summary["unique_hosts"] = df["hostname"].nunique()
            payload = {
                "data": [summary],
                "count": 1,
                "columns": list(summary.keys()),
                "table": table,
            }
        payload["__meta__"] = {"elapsed_sec": round(time.perf_counter() - start, 6)}
        return payload
    except Exception as e:
        logger.error(f"Failed querying parquet for table={table}: {e}", exc_info=True)
        return {
            "error": f"Query failure: {e}",
            "table": table,
            "method": method,
            "__meta__": {"elapsed_sec": round(time.perf_counter() - start, 6)},
        }

