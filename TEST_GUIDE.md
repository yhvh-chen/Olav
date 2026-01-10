# 🧪 Test Execution Guide

**Date**: 2026-01-09
**Status**: 245/245 Tests Passing (100%)

---

## 📊 Test Categories

### Unit Tests (Fast, No External Dependencies)
```bash
# Run all unit tests
uv run pytest tests/unit/ -v

# Run with coverage
uv run pytest tests/unit/ -v --cov=src/olav --cov-report=term-missing

# Run specific test file
uv run pytest tests/unit/test_report_formatter.py -v

# Run specific test class
uv run pytest tests/unit/test_report_formatter.py::TestFormatInspectionReport -v

# Run specific test
uv run pytest tests/unit/test_report_formatter.py::TestFormatInspectionReport::test_markdown_format_english -v
```

### Integration Tests (Requires External Services)
```bash
# Run all integration tests
uv run pytest tests/integration/ -v -m integration

# Run LLM integration tests (requires API keys)
uv run pytest tests/integration/test_llm_integration.py -v -m integration -m llm

# Skip slow tests
uv run pytest tests/integration/ -v -m integration -m "not slow"
```

### E2E Tests (Requires Network Devices)
```bash
# Run all E2E tests
uv run pytest tests/e2e/ -v -m e2e

# Run network device tests (requires devices configured)
uv run pytest tests/e2e/test_network_devices.py -v -m e2e -m network

# Run real device tests
uv run pytest tests/e2e/ -v -m real_devices

# Skip slow tests
uv run pytest tests/e2e/ -v -m e2e -m "not slow"
```

### Combined Test Runs
```bash
# Run unit tests only (fastest)
uv run pytest -m "unit" -v

# Run unit + integration (no network devices)
uv run pytest -m "unit or integration" -v

# Run all tests (will skip integration/e2e without infrastructure)
uv run pytest -v

# Run with coverage and HTML report
uv run pytest -v --cov=src/olav --cov-report=html --cov-report=term-missing
```

---

## 🏷️ Test Markers

### Markers Available
- `unit`: Unit tests (fast, no external dependencies)
- `integration`: Integration tests (requires external services)
- `e2e`: End-to-end tests (requires full infrastructure)
- `llm`: Tests requiring real LLM API calls
- `network`: Tests requiring network device access
- `slow`: Slow-running tests
- `real_devices`: Tests requiring real device connectivity via Nornir

### Marker Usage Examples
```bash
# Run only fast unit tests
uv run pytest -m "unit and not slow" -v

# Run LLM tests
uv run pytest -m "llm" -v

# Run network tests
uv run pytest -m "network" -v

# Run tests that don't require real infrastructure
uv run pytest -m "not real_devices and not llm" -v

# Run all tests except slow ones
uv run pytest -m "not slow" -v
```

---

## 🔧 Prerequisites

### For Unit Tests
```bash
# No prerequisites required
# Just run:
uv run pytest tests/unit/ -v
```

### For LLM Integration Tests
```bash
# Set up environment variables in .env:
OPENAI_API_KEY=your_key_here
# or
LLM_API_KEY=your_key_here

# Then run:
uv run pytest tests/integration/test_llm_integration.py -v -m llm
```

### For Network E2E Tests
```bash
# Prerequisites:
# 1. Nornir configured in .olav/config/nornir/ (or .claude/config/nornir/)
# 2. Network devices accessible
# 3. Credentials in .env:
DEVICE_USERNAME=your_username
DEVICE_PASSWORD=your_password
DEVICE_ENABLE_PASSWORD=your_enable_password

# Then run:
uv run pytest tests/e2e/test_network_devices.py -v -m network
```

---

## 📈 Current Test Status

### Summary
```
Total Tests: 245
Passing: 245 (100%)
Failing: 0
Coverage: 54% overall (90-100% on critical modules)
```

### Coverage by Module
```
cli/memory.py                    100%
core/subagent_manager.py         100%
core/diagnosis_middleware.py      94%
tools/inspection_tools.py         96%
tools/report_formatter.py         96%
core/settings.py                  91%
core/learning.py                  90%
core/skill_router.py              85%
core/skill_loader.py              79%
cli/input_parser.py               84%
```

---

## 🐛 Debugging Failed Tests

### Get Detailed Output
```bash
# Show full tracebacks
uv run pytest tests/unit/test_report_formatter.py -v --tb=long

# Show output on failure
uv run pytest tests/unit/test_report_formatter.py -v --tb=short -s

# Stop on first failure
uv run pytest tests/unit/ -v -x

# Enter debugger on failure
uv run pytest tests/unit/test_report_formatter.py -v --pdb
```

### Run Specific Tests
```bash
# Run failed tests only
uv run pytest --lf -v

# Run failed tests first
uv run pytest --ff -v

# Run tests by keyword
uv run pytest -k "markdown" -v
```

---

## 📝 Test Files

### Unit Tests (245 tests)
```
tests/unit/test_report_formatter.py       14 tests
tests/unit/test_skill_loader.py           16 tests
tests/unit/test_phase5_inspection.py      45 tests
tests/unit/test_phase5_inspection_tools.py 60 tests
tests/unit/test_phase5_simple.py          15 tests
tests/unit/test_subagent_manager.py       8 tests
tests/unit/test_subagent_configs.py       6 tests
tests/unit/test_skill_router.py           12 tests
tests/unit/test_textfsm_parsing.py        8 tests
tests/unit/test_settings.py               10 tests
tests/unit/test_cli_commands.py           51 tests
```

### Integration Tests (Skeletons)
```
tests/integration/test_llm_integration.py  215 lines
- LLM initialization tests
- Skill router integration tests
- Performance benchmarks
- Error handling tests
```

### E2E Tests (Skeletons)
```
tests/e2e/test_network_devices.py  350 lines
- Device connectivity tests
- Health check workflow tests
- Configuration backup tests
- Performance tests
```

---

## 🎯 Quick Commands

### Most Common Commands
```bash
# Quick test run (unit tests only)
uv run pytest tests/unit/ -v

# Full test run with coverage
uv run pytest -v --cov=src/olav --cov-report=term-missing

# Run with coverage and ignore fail-under
uv run pytest tests/unit/ -v --cov=src/olav --no-cov-on-fail

# Run specific test file
uv run pytest tests/unit/test_report_formatter.py -v

# Run integration tests (with API keys)
uv run pytest tests/integration/ -v -m integration

# Run network tests (with devices)
uv run pytest tests/e2e/test_network_devices.py -v -m network
```

---

## 📊 Coverage Goals

### Current Status
- **Overall**: 54% (up from 19%)
- **Critical Modules**: 90-100%
- **Production Ready**: Yes ✅

### Future Goals
- Target: 70% overall coverage
- Priority modules > 90%
- All critical paths covered

---

**Generated**: 2026-01-09
**Test Status**: 245/245 PASSING ✅
**Coverage**: 54%
**Production Ready**: Yes ✅
