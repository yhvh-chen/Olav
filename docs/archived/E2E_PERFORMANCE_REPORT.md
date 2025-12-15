# OLAV E2E Performance Testing Report

**Date**: 2025-12-06  
**LLM Provider**: Ollama  
**Model**: qwen3-coder:latest  
**Environment**: Windows 11, local development

## Executive Summary

| Metric | Value |
|--------|-------|
| **Tests Passed** | 10/12 (83.3%) |
| **Average LLM Time** | 1,494ms |
| **Fastest LLM Call** | 354ms (Expert Mode) |
| **Slowest LLM Call** | 5,780ms (Cold start) |
| **Average Total Time** | 1,878ms |

## Test Results by Mode

### Standard Mode (6/8 passed - 75%)

| Query | Total Time | LLM Time | LLM % | Status |
|-------|------------|----------|-------|--------|
| 查询 R1 的 BGP 状态 | 5,881ms | 5,780ms | 98% | ✅ Pass |
| 显示所有设备的接口状态 | 1,889ms | 1,837ms | 97% | ✅ Pass |
| R1 的 OSPF 邻居有哪些 | 1,628ms | 488ms | 30% | ❌ Fail |
| 检查 spine-1 的路由表 | 1,755ms | 1,663ms | 95% | ✅ Pass |
| 查看 core-rtr 的 BGP 会话 | 1,685ms | 1,671ms | 99% | ✅ Pass |
| 列出所有设备 | 1,501ms | 1,356ms | 90% | ✅ Pass |
| R1 有多少个接口是 up 状态 | 1,849ms | 1,799ms | 97% | ✅ Pass |
| 查询 leaf-1 的 VXLAN 状态 | 1,208ms | 362ms | 30% | ❌ Fail |

**Failure Analysis**:
1. **OSPF Query**: No OSPF data in SuzieQ parquet - data availability issue, not code
2. **VXLAN Query**: `SuzieQTool.execute() missing 1 required positional argument: 'table'` - LLM generated incomplete parameters

### Expert Mode (3/3 passed - 100%)

| Query | Total Time | LLM Time | Rounds | Status |
|-------|------------|----------|--------|--------|
| 为什么 R1 和 R2 之间的 BGP 会话建立失败 | 973ms | 680ms | 5 | ✅ Pass |
| 分析 spine-1 的网络连通性问题 | 512ms | 358ms | 5 | ✅ Pass |
| 诊断 leaf-1 无法 ping 通 leaf-2 的原因 | 506ms | 354ms | 5 | ✅ Pass |

### Inspection Mode (1/1 passed - 100%)

| Config | Total Time | Checks | Status |
|--------|------------|--------|--------|
| temp_inspection.yaml | 100ms | 2/2 | ✅ Pass |

**Note**: Inspection Mode is rule-based and does not use LLM.

## Performance Analysis

### Key Findings

#### 1. Cold Start Penalty (5.8s → 1.5s)

The first LLM call takes ~5,780ms while subsequent calls average ~1,500ms. This is **3.8x slower** due to Ollama model loading.

**Recommendation**: Implement model prewarming on CLI startup or use persistent model serving.

#### 2. LLM is the Dominant Bottleneck (90-99%)

In Standard Mode, LLM inference accounts for 90-99% of total execution time.

```
┌────────────────────────────────────────────────┐
│ Total Time Breakdown (Standard Mode Avg)       │
├────────────────────────────────────────────────┤
│ ████████████████████████████████████░░░░ 95%   │ LLM Inference
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  5%   │ Tool Execution
└────────────────────────────────────────────────┘
```

**Recommendation**: 
- Consider smaller/faster models for simple classification
- Implement response caching for repeated queries
- Batch similar queries to reduce overhead

#### 3. Expert Mode is Paradoxically Fast (~500ms)

Expert Mode diagnostic queries complete in 500-1000ms despite running 5 rounds. This is because:
- SuzieQ tools are mocked (not connecting to real database)
- LLM calls are smaller (diagnostic planning vs. tool selection)

**In production with real SuzieQ**: Expect 5-10x longer execution.

#### 4. Token Efficiency

| Mode | Avg Input Tokens | Avg Output Tokens | Token Ratio |
|------|------------------|-------------------|-------------|
| Standard | 51 | 51 | 1:1 |
| Expert | 33 | 16 | 2:1 |

Output tokens are reasonable, but input tokens could be reduced by:
- Shortening system prompts
- Using few-shot examples selectively

### Graph State Timeline (Standard Mode)

```
Query: "查询 R1 的 BGP 状态"

┌─────────────────────────────────────────────────────────────┐
│  0ms        1500ms       3000ms       4500ms       5881ms   │
│  │            │            │            │            │      │
│  ├─── classify ──────────────────────────────────────┤      │
│  │          [LLM: 5780ms]                            │      │
│  │                                                   │      │
│  │                                            execute┤      │
│  │                                           [101ms] │      │
└─────────────────────────────────────────────────────────────┘
```

## Recommendations for Performance Improvement

### Short-term (Quick Wins)

1. **Model Prewarming** - Call a dummy classify on startup to load model
2. **Response Caching** - Cache LLM responses for identical queries (5min TTL)
3. **Streaming Output** - Show partial results as LLM generates

### Medium-term (Architecture)

1. **Two-Stage Classification**
   - Stage 1: Fast regex/keyword matcher for obvious queries
   - Stage 2: LLM for ambiguous cases only

2. **Async Parallel Execution**
   - While LLM classifies, prefetch likely tool schemas
   - Run multiple independent tool calls in parallel

3. **Smaller Classification Model**
   - Use quantized model (qwen3-coder-q4) for classification
   - Full model only for complex reasoning

### Long-term (Infrastructure)

1. **GPU Acceleration**
   - Move from CPU Ollama to GPU inference
   - Expected: 10-50x speedup

2. **Model Serving**
   - Deploy vLLM/TensorRT-LLM for production
   - Enable continuous batching

3. **Distributed Caching**
   - Redis cache for cross-user query deduplication
   - Semantic similarity matching for cache hits

## Appendix: Raw Metrics

### Token Distribution

```
Standard Mode Tokens:
  Query 1: 288 total (144 in + 144 out)
  Query 2:  90 total (45 in + 45 out)
  Query 3:  24 total (12 in + 12 out) - FAILED
  Query 4:  82 total (41 in + 41 out)
  Query 5:  82 total (41 in + 41 out)
  Query 6:  66 total (33 in + 33 out)
  Query 7:  88 total (44 in + 44 out)
  Query 8:  18 total (9 in + 9 out)  - FAILED
  
Expert Mode Tokens:
  Query 1: 72 total (48 in + 24 out)
  Query 2: 37 total (25 in + 12 out)
  Query 3: 37 total (25 in + 12 out)
```

### Log Files

- Full test log: `tests/e2e/logs/e2e_perf_20251206_180842.jsonl`
- Standard Mode only: `tests/e2e/logs/e2e_perf_20251206_180333.jsonl`
- Expert Mode only: `tests/e2e/logs/e2e_perf_20251206_180817.jsonl`

---

*Generated by e2e_perf_test.py on 2025-12-06*
