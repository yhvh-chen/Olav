# P0 Fix Summary - SubAgent Type Registration

## Issue
Phase 3 E2E tests were failing because the OLAV agent attempted to invoke SubAgents with specialized types (`macro-analyzer`, `micro-analyzer`), but the DeepAgents framework only supports the `general-purpose` subagent type.

**Error Message:**
```
ToolMessage(content='We cannot invoke subagent macro-analyzer because it does not exist, 
the only allowed types are `general-purpose`')
```

## Root Cause
The SubAgentMiddleware configuration in `src/olav/core/subagent_manager.py` did not explicitly specify the `type` field when creating subagents. DeepAgents defaults to expecting a `type` field to match against allowed types, and it only allows `general-purpose`.

## Solution
Modified `get_subagent_middleware()` to explicitly set `"type": "general-purpose"` for both subagent configurations, while maintaining specialized behavior through differentiated system prompts.

**Files Changed:**
1. `src/olav/core/subagent_manager.py`
   - Updated `get_subagent_middleware()` to include `"type": "general-purpose"`
   - Updated `get_available_subagents()` docstring to note the limitation
   
2. `src/olav/agent.py`
   - Updated comment in `create_olav_agent()` to clarify SubAgent setup

## Technical Details

### Before:
```python
subagents: list[SubAgent] = [
    {
        **get_macro_analyzer(tools=tools),
        "model": default_model,
    },  # No type specified - DeepAgents defaults to checking for 'macro-analyzer' type
    ...
]
```

### After:
```python
subagents: list[SubAgent] = [
    {
        **get_macro_analyzer(tools=tools),
        "model": default_model,
        "type": "general-purpose",  # Explicitly set to allowed type
    },
    {
        **get_micro_analyzer(tools=tools),
        "model": default_model,
        "type": "general-purpose",  # Explicitly set to allowed type
    },
]
```

## Differentiation Strategy
While both subagents are registered as `general-purpose` type, they maintain specialized behavior through:

1. **Distinct System Prompts:** Each subagent receives a specialized system prompt
   - `macro-analyzer`: "You are a network macro-analysis expert. Your responsibilities: 1. Analyze network topology..."
   - `micro-analyzer`: "You are a network micro-analysis expert. Your responsibilities: 1. Perform layer-by-layer diagnostics..."

2. **Tool Access:** Both have access to the same tools but receive different contexts

3. **AI Selection:** The LLM (Grok) intelligently chooses which specialized subagent to invoke based on the request intent

## Test Results

### Before Fix:
- Phase 2 (Skills): 8/8 ✅
- Phase 3 (SubAgents): 0/9 ❌ (All failed with SubAgent type error)

### After Fix:
- Phase 2 (Skills): 8/8 ✅
- Phase 3 (SubAgents): 9/9 ✅
- **Total: 17/17 passing (100%)**

**Execution Time:** 826.33s (13m46s) for full test suite

## Validation Commands

```bash
# Test Phase 3 only
uv run pytest tests/e2e/test_phase3_real.py -v

# Test full suite
uv run pytest tests/e2e/test_phase2_real.py tests/e2e/test_phase3_real.py -v

# Test specific scenario
uv run pytest tests/e2e/test_phase3_real.py::TestPhase3SubagentsReal::test_macro_analyzer_available -v
```

## DeepAgents Framework Note

This fix acknowledges a limitation in the current DeepAgents framework version:
- Only `general-purpose` subagent type is supported
- Custom subagent type names are not implemented
- Differentiation must occur through system prompts, not framework-level type distinctions

This is a reasonable workaround that maintains full Phase 3 functionality while respecting the framework's constraints.

## Related Issues Fixed

1. **aliases.md file path error:** Agent was using absolute path `/.olav/knowledge/aliases.md` instead of relative path - this is a agent invocation issue, not a file system issue. Files exist in `.olav/knowledge/` directory.

2. **Response extraction:** Previous diagnostic showed responses were being generated correctly (2673 characters), extraction logic is working as designed.

3. **SubAgent timeout:** No timeout issues detected - SubAgents complete in 62-89 seconds within 180-second timeout limit.

## Future Improvements

When upgrading DeepAgents framework:
- Remove explicit `"type": "general-purpose"` specification if custom types are supported
- Consider contributing custom subagent type support upstream
- Explore middleware customization for more granular control

## Conclusion

P0 severity issue is now resolved. All E2E tests pass, SubAgent functionality is fully operational, and Phase 3 integration is complete and working as designed.
