# Manual Testing Quick Start Guide

**Location**: `tests/manual/`  
**How to Run**: `uv run python tests/manual/run_all.py`  
**Duration**: ~2-3 minutes for all tests

## Quick Command Reference

```bash
# Run all tests
uv run python tests/manual/run_all.py

# Run specific test
uv run python tests/manual/test_01_agent_creation.py
uv run python tests/manual/test_02_simple_query.py
uv run python tests/manual/test_03_skill_routing.py
uv run python tests/manual/test_04_nornir_devices.py
uv run python tests/manual/test_05_quick_query.py
uv run python tests/manual/test_06_error_handling.py
```

## What Each Test Does

### test_01_agent_creation.py ⏱️ ~5 seconds
Tests that the OLAV agent can be initialized correctly.

**Expected Output**:
```
✅ 基础 agent 创建成功
✅ 完整 agent 创建成功
✅ Agent 支持同步调用 (invoke)
✅ Agent 支持异步调用 (ainvoke)
```

### test_02_simple_query.py ⏱️ ~15 seconds
Tests basic query responses and output quality.

**Expected Output**: 3 queries with 80/100 quality scores

### test_03_skill_routing.py ⏱️ ~10 seconds
Tests that different queries are routed to correct skills.

**Expected Output**: 9/10 exact matches, 1 fallback

### test_04_nornir_devices.py ⏱️ ~10 seconds
Tests device connectivity and Nornir configuration.

**Expected Output**: 6 devices listed, command executes on R1

### test_05_quick_query.py ⏱️ ~15 seconds
Tests Quick Query skill output quality.

**Expected Output**: 3 queries with 6/6 perfect scores

### test_06_error_handling.py ⏱️ ~15 seconds
Tests error scenarios and graceful handling.

**Expected Output**: 5 error scenarios, all graceful (0 crashes)

## Expected Success Criteria

| Test | Metric | Expected |
|------|--------|----------|
| test_01 | Creation | 2/2 agents ✅ |
| test_02 | Quality | 3/3 queries at 80/100 ✅ |
| test_03 | Routing | 9/10 exact matches ✅ |
| test_04 | Devices | 6 devices online ✅ |
| test_05 | Output | 3/3 queries at 6/6 ✅ |
| test_06 | Errors | 5/5 graceful ✅ |

## Troubleshooting

### ❌ "OPENAI_API_KEY not set"
**Solution**: Check that `.env` file exists and contains valid `LLM_API_KEY`
```bash
# Verify .env exists
ls -la .env

# Check the variable is set
uv run python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('LLM_API_KEY' in os.environ)"
```

### ❌ "Device not found"
**Solution**: Nornir is configured for a lab environment. Tests will show which devices are available.

### ❌ "Module not found"
**Solution**: Ensure you're using `uv run` not plain `python`:
```bash
# ❌ Wrong
python tests/manual/test_01_agent_creation.py

# ✅ Correct
uv run python tests/manual/test_01_agent_creation.py
```

### ❌ Test hangs or times out
**Solution**: Reduce by pressing Ctrl+C and check:
1. Network connectivity
2. LLM API access
3. Device connectivity
4. Check for blocking operations

## Key Patterns Used

### 1. LLMFactory for API Keys
```python
from src.olav.core.llm import LLMFactory
llm = LLMFactory.get_chat_model()  # Handles .env mapping correctly
```

### 2. StructuredTool Invocation
```python
from src.olav.tools.network import list_devices
result = list_devices.invoke({})  # Not list_devices()
```

### 3. Agent Invocation
```python
from src.olav.agent import create_olav_agent
agent = create_olav_agent()
response = agent.invoke({
    "messages": [{"role": "user", "content": "查询 R1 接口状态"}]
})
```

## Test Output Interpretation

### Quality Scores
- **80/100**: Excellent - Production ready
- **6/6**: Perfect - All criteria met
- **90%**: Good - 9/10 tests passed

### Status Symbols
- ✅ Success
- ❌ Failure
- ⚠️ Warning/Partial
- 📋 Information

## Performance Benchmarks

From actual test runs:

| Operation | Duration | Status |
|-----------|----------|--------|
| Agent creation | <1 sec | ✅ |
| Simple query | 3-5 sec | ✅ |
| Skill routing | 2-3 sec | ✅ |
| Device list | <1 sec | ✅ |
| Nornir command | 2-3 sec | ✅ |
| Error handling | 1-2 sec | ✅ |
| **Total** | ~1-2 min | ✅ |

## Next Actions

If all tests pass: ✅
- System is production-ready
- No action required
- Monitor in production

If any test fails: ❌
1. Check the error message
2. Refer to troubleshooting section
3. Fix the issue
4. Re-run test to verify

## Documentation References

- **Manual Test Results**: See `MANUAL_TEST_RESULTS.md` for detailed results
- **Configuration**: See `.olav/settings.json` for behavior preferences  
- **Architecture**: See `DESIGN_V0.8.md` for system design
- **CLI Guide**: See `docs/CLI_USER_GUIDE.md` for command examples

## Support

For issues:
1. Check test output messages
2. Review `MANUAL_TEST_RESULTS.md` for known patterns
3. Check logs in `.olav/` directory
4. Review `.env` configuration

