# Quick Reference: OLAV v0.8 E2E Test Suite

## Run Tests

### All Tests
```bash
cd c:\Users\yhvh\Documents\code\Olav
pytest tests/e2e/test_skill_system_e2e.py -v
```

### Specific Test Class
```bash
# Skill Routing Tests
pytest tests/e2e/test_skill_system_e2e.py::TestSkillRouting -v

# Batch Query Tests
pytest tests/e2e/test_skill_system_e2e.py::TestBatchQueryTool -v

# Guard Filter Tests
pytest tests/e2e/test_skill_system_e2e.py::TestGuardIntentFilter -v

# Device Connectivity Tests
pytest tests/e2e/test_skill_system_e2e.py::TestRealDeviceConnectivity -v

# Tool Integration Tests
pytest tests/e2e/test_skill_system_e2e.py::TestToolIntegration -v

# Skill Metadata Tests
pytest tests/e2e/test_skill_system_e2e.py::TestSkillMetadata -v
```

### Specific Test
```bash
pytest tests/e2e/test_skill_system_e2e.py::TestSkillRouting::test_simple_query_interface_status -v
```

## Test Results

```
Status:     ✅ 15/15 PASSING
Time:       ~190 seconds (3.2 minutes)
Devices:    6 real Cisco IOS devices (R1-R4, SW1-SW2)
Commands:   79 approved Cisco IOS commands
```

## File Locations

### Test Files
- **E2E Test Suite**: `tests/e2e/test_skill_system_e2e.py` (263 lines)
- **Detailed Report**: `docs/E2E_TEST_COMPLETION.md` (320 lines)
- **Summary**: `E2E_TEST_SUMMARY.md`
- **Verification**: `E2E_TESTS_VERIFICATION.md`

### Configuration
- **Aliases**: `.olav/knowledge/aliases.md`
- **Pytest Config**: `pyproject.toml`
- **Skills Directory**: `.olav/skills/`

### Source Code
- **Skill Loader**: `src/olav/core/skill_loader.py` (130 lines)
- **Skill Router**: `src/olav/core/skill_router.py` (200 lines)
- **Agent Integration**: `src/olav/agent.py` (269 lines)

## Test Categories (6)

1. **TestSkillRouting** (4 tests)
   - Simple queries on real devices
   - Interface, BGP, OSPF, VLAN

2. **TestBatchQueryTool** (1 test)
   - Batch query across all devices

3. **TestGuardIntentFilter** (2 tests)
   - Network/non-network classification

4. **TestRealDeviceConnectivity** (3 tests)
   - R1, R2, SW1 accessibility

5. **TestToolIntegration** (2 tests)
   - Command selection, alias resolution

6. **TestSkillMetadata** (3 tests)
   - Skill loading, metadata, routing

## Real Devices

```
R1  192.168.100.101  ✅ Accessible
R2  192.168.100.102  ✅ Accessible
R3  192.168.100.103  ✅ Accessible
R4  192.168.100.104  ✅ Accessible
SW1 192.168.100.105  ✅ Accessible
SW2 192.168.100.106  ✅ Accessible
```

## Skills Loaded

```
✅ quick-query (simple queries)
✅ device-inspection (inspection operations)
✅ network-diagnosis (diagnostic queries)
✅ deep-analysis (complex analysis)
✅ configuration-management (config operations)
```

## Quick Verify

To quickly verify everything is working:

```bash
# Check pytest can find all tests
pytest tests/e2e/test_skill_system_e2e.py --collect-only -q

# Run tests with minimal output
pytest tests/e2e/test_skill_system_e2e.py -v --tb=no

# Run with summary only
pytest tests/e2e/test_skill_system_e2e.py --tb=no -q
```

## Troubleshooting

### Tests not found
```bash
# Ensure you're in the right directory
cd c:\Users\yhvh\Documents\code\Olav

# Verify test file exists
ls tests/e2e/test_skill_system_e2e.py
```

### Tests timeout
Default timeout is 30 seconds per test. If tests timeout:
1. Check network connectivity to devices (192.168.100.x)
2. Verify SSH credentials in `.env` file
3. Check device is responding: `ping 192.168.100.101`

### Device not accessible
```bash
# Test connectivity
ping 192.168.100.101
ssh admin@192.168.100.101

# Check Nornir inventory
cat config/nornir_config.yml

# Verify device credentials
cat .env | grep DEVICE_
```

## Advanced Options

### Run with coverage
```bash
pytest tests/e2e/test_skill_system_e2e.py -v --cov=olav --cov-report=html
```

### Run with markers
```bash
# Run only slow tests
pytest tests/e2e/test_skill_system_e2e.py -v -m slow

# Run all except slow tests
pytest tests/e2e/test_skill_system_e2e.py -v -m "not slow"
```

### Verbose output
```bash
# Show full tracebacks
pytest tests/e2e/test_skill_system_e2e.py -v --tb=long

# Show print statements
pytest tests/e2e/test_skill_system_e2e.py -v -s
```

### Parallel execution (requires pytest-xdist)
```bash
# Run 4 tests in parallel
pytest tests/e2e/test_skill_system_e2e.py -n 4
```

## Status Summary

| Component | Status | Tests |
|-----------|--------|-------|
| Skill Routing | ✅ | 4 |
| Batch Query | ✅ | 1 |
| Guard Filter | ✅ | 2 |
| Real Devices | ✅ | 3 |
| Tool Integration | ✅ | 2 |
| Skill Metadata | ✅ | 3 |
| **Total** | **✅** | **15** |

## Key Metrics

- **Pass Rate**: 100% (15/15)
- **Execution Time**: ~190 seconds
- **Real Devices**: 6 (all accessible)
- **Approved Commands**: 79
- **Skills Loaded**: 5
- **Test Categories**: 6

## Next Steps

Phase 2 work items (non-blocking):
1. Optimize diagnostic skill (complex queries)
2. Optimize inspection skill (batch operations)
3. Expand aliases.md (service mappings)
4. Add performance benchmarking

---

OLAV v0.8 - Network Operations AI with DeepAgents + Skill System
Generated: 2024-12-15
