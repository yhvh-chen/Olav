# OLAV Code Audit Report

Generated: 2025-12-08

## Summary

After thorough audit of `config/` and `src/olav/` directories:

### Actions Taken
- **Deleted 2 unused files**
- **Fixed 5 dead code instances** (vulture findings)
- **Removed 1 unused import**
- **Verified 23 false positives** (entry points, ETL scripts)

### Test Results
- ✅ **680 passed**, 7 skipped, 8 warnings

---

## 1. Files Deleted (Truly Unused)

These files are not imported anywhere and have no external usage:

| File | Reason | Action |
|------|--------|--------|
| `src/olav/core/state.py` | Legacy state definitions, replaced by `olav.workflows.base.BaseWorkflowState` | DELETE |
| `src/olav/tools/unified_schema_tool.py` | Tool defined but never used anywhere in codebase | DELETE |

---

## 2. Files to KEEP (False Positives)

These appear unused by import analysis but are actually used:

### Entry Points (pyproject.toml / cli.py)
- `src/olav/cli/commands.py` - Main CLI entry point (`olav` command)
- `src/olav/cli/auth.py` - Used by cli/__init__.py exports
- `src/olav/cli/client.py` - Used by cli/__init__.py exports
- `src/olav/cli/display.py` - Used by repl.py
- `src/olav/cli/repl.py` - Used by commands.py
- `src/olav/admin/commands.py` - Admin CLI entry point (`olav-admin` command)
- `src/olav/studio.py` - LangGraph Studio entry point (langgraph.json)

### ETL Scripts (invoked via `uv run python -m`)
- `src/olav/etl/init_all.py` - Master ETL orchestrator
- `src/olav/etl/init_postgres.py` - PostgreSQL initialization
- `src/olav/etl/init_schema.py` - Schema index initialization
- `src/olav/etl/init_docs.py` - Document indexing
- `src/olav/etl/init_diagnosis_kb.py` - Diagnosis knowledge base
- `src/olav/etl/init_episodic_memory.py` - Memory index initialization
- `src/olav/etl/init_syslog_index.py` - Syslog index initialization
- `src/olav/etl/suzieq_schema_etl.py` - SuzieQ schema ETL
- `src/olav/etl/netbox_schema_etl.py` - NetBox schema ETL
- `src/olav/etl/openconfig_full_yang_etl.py` - OpenConfig YANG ETL
- `src/olav/etl/embedder.py` - Embedding service
- `src/olav/etl/generate_configs.py` - Config generation

### Server Components
- `src/olav/server/app.py` - FastAPI server (invoked via uvicorn)
- `src/olav/server/jobs.py` - Background job processing

### Workflows
- `src/olav/workflows/device_inspector.py` - Used by supervisor_driven.py
- `src/olav/inspection/executor.py` - Used by server and CLI

---

## 3. Dead Code (FIXED)

All vulture findings have been fixed:

| File | Line | Issue | Status |
|------|------|-------|--------|
| `src/olav/cli/client.py` | 569 | Duplicate return statement | ✅ FIXED |
| `src/olav/cli/repl.py` | 107 | Unused variable 'complete_event' | ✅ FIXED (prefixed with _) |
| `src/olav/execution/backends/nornir_sandbox.py` | 223 | Unused variable 'background' | ✅ FIXED (prefixed with _) |
| `src/olav/execution/backends/protocol.py` | 60 | Unused variable 'background' | ✅ FIXED (prefixed with _) |
| `src/olav/workflows/deep_dive.py` | 1058 | Unused variable 'purpose' | ✅ FIXED (now used in error messages) |
| `src/olav/admin/commands.py` | 18 | Unused import 'Optional' | ✅ FIXED (removed) |

---

## 4. Deprecated Methods to Remove

In `src/olav/core/prompt_manager.py`:
- Line 197: `load_agent_prompt()` - DEPRECATED: Use load() instead
- Line 246: `load_tool_description()` - DEPRECATED: Use load() instead  
- Line 260: `load_workflow_prompt()` - DEPRECATED: Use load() instead
- Line 274: `load_system_prompt()` - DEPRECATED: Use load() instead

---

## 5. TODO/FIXME Comments (33 total)

Key actionable items:

| File | Line | Comment |
|------|------|---------|
| `src/olav/cli/client.py` | 322 | Remote mode: TODO - implement remote resume via API |
| `src/olav/core/middleware/filesystem.py` | 175 | TODO: Implement OpenSearch client integration |
| `src/olav/core/middleware/filesystem.py` | 204 | TODO: Implement LangGraph interrupt for HITL |
| `src/olav/core/middleware/filesystem.py` | 217 | Auto-approve for now (TODO: implement real HITL) |

Most other TODOs are in docs or are valid work items.

---

## 6. Recommended Actions

### Completed ✅
1. ~~Delete `src/olav/core/state.py`~~ DONE
2. ~~Delete `src/olav/tools/unified_schema_tool.py`~~ DONE
3. ~~Fix unreachable code in `src/olav/cli/client.py:569`~~ DONE
4. ~~Remove unused variables in affected files~~ DONE
5. ~~Remove unused import in `src/olav/admin/commands.py`~~ DONE

### Future Work
1. Remove deprecated methods from `prompt_manager.py` after verifying no usage
2. Address filesystem.py TODO items for HITL implementation
3. Consider consolidating deprecated CLI command aliases

---

## 7. Verification Commands

```bash
# Verify no imports of deleted files
git grep "olav.core.state"
git grep "unified_schema_tool"

# Run tests after cleanup
uv run pytest tests/unit/ -q --tb=short

# Re-run audit
uv run python scripts/audit_quick.py
```
