# Performance Optimization Guide

This guide explains how to profile and optimize OLAV query performance across SuzieQ (read), NETCONF/Nornir (write/read), and CLI fallback operations.

## 1. Built-in Timing Metadata
Both `suzieq_query` (class + standalone tool) now return a `__meta__` block:
```json
{
  "data": [...],
  "table": "interfaces",
  "method": "top",
  "__meta__": {"elapsed_sec": 0.012345}
}
```
Use this to surface latency in responses or aggregate in episodic memory for trend tracking.

### Action Items
- Add similar timing to NETCONF (`nornir_tool`) and CLI tool functions.
- Aggregate per-tool latency for multi-step queries.

## 2. LangChain / DeepAgents Profiling
Use LangChain Studio (or built-in tracing) to inspect:
- Token usage per iteration
- Tool call sequence & parallelism
- Repeated schema searches (cache them to Postgres or Redis)

### Steps
1. Export `LANGCHAIN_TRACING_V2=true` and set project name.
2. Run: `uv run python -m olav.main chat "查询设备 R1 的接口状态"`
3. Inspect spans: slowest spans typically are network I/O or large summarizations.

## 3. Reducing Unnecessary Tool Calls
Pattern: LLM often re-calls `suzieq_schema_search`. Mitigation:
- Maintain an in-memory cache keyed by thread_id & table list.
- Return cached schema when identical query text AND tables unchanged.

## 4. Batch Strategy for Interface / Route Health
Instead of per-device calls:
- Prefer SuzieQ summarize for global view.
- Fall back to targeted NETCONF only for anomalies.

## 5. Concurrency Considerations
SuzieQ operations are local DataFrame scans; heavy parallelization may hurt due to GIL. Strategy:
- Keep them synchronous but ensure network I/O (NETCONF) is async.
- Bound concurrent NETCONF sessions to avoid device overload (e.g., semaphore of 8).

## 6. Future Enhancements
| Enhancement | Description | Priority |
|-------------|-------------|----------|
| NETCONF timing | Wrap Nornir runs with perf counters | High |
| Aggregated latency report | Summarize per-query tool timings in final agent message | High |
| Schema search cache | Avoid duplicate schema discovery work | Medium |
| Pydantic models | Faster validation + structured meta | Medium |
| Async OpenSearch writes | Non-blocking audit logging | Low |

## 7. Quick Checklist
- [ ] Timing decorator on NETCONF tool
- [ ] Timing decorator on CLI tool
- [ ] Latency aggregation in root agent final message
- [ ] Schema cache implementation
- [ ] Tracing enabled in non-prod environments

## 8. Troubleshooting Slow Queries
| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| High elapsed_sec in summarize | Large DataFrame scan | Add selective filters (namespace/hostname) |
| Multiple identical schema searches | No caching layer | Add thread-level cache dict |
| NETCONF spikes | Device rate limiting | Introduce concurrency semaphore |
| CLI fallback frequent | NETCONF path failing | Improve degradation detection logic |

## 9. Metrics to Track
- `latency.suzieq.get/summarize/top` (histogram)
- `latency.netconf.exec`
- `latency.cli.exec`
- `count.suzieq.schema_search.cache_hits` / `misses`
- `count.hitl.approvals` / `rejections`

## 10. Next Steps
Implement decorators for remaining tools, add aggregation in final agent response, then persist metrics in OpenSearch for longitudinal analysis.
