# OLAV Batch Inspection Configurations

This directory contains YAML configuration files for declarative batch network inspections.

## Overview

Batch inspections enable:
- **Declarative configuration**: Define checks in YAML, not code
- **Version control**: Track inspection logic changes in Git
- **Parallel execution**: Efficient multi-device checks (10-100+ devices)
- **Zero-LLM validation**: Deterministic threshold checks using Python operators
- **Automated scheduling**: Integrate with cron/APScheduler for daily/weekly runs

## Directory Structure

```
config/inspections/
├── README.md                    # This file
├── bgp_peer_audit.yaml         # BGP health check example
├── interface_health.yaml       # Interface error/utilization check
├── daily_core_check.yaml       # Comprehensive core network audit
└── (your custom configs)
```

## YAML Schema

Each inspection config follows this structure:

```yaml
name: inspection_job_name           # Unique identifier
description: Human-readable purpose

# Device Selection (choose ONE)
devices:
  - R1                              # Option 1: Explicit list
  - R2

# OR
devices:
  netbox_filter:                    # Option 2: NetBox query
    role: router
    site: DC1
    tag: production

# OR
devices:
  regex: "^R[0-9]+"                 # Option 3: Regex pattern

# Inspection Checks
checks:
  - name: check_name
    description: What this check does
    tool: suzieq_query              # Tool to execute
    enabled: true                   # Enable/disable check
    parameters:                     # Tool-specific parameters
      table: bgp
      state: Established
    threshold:                      # Validation rule
      field: count                  # Field to check
      operator: ">="                # Comparison operator
      value: 2                      # Expected value
      severity: critical            # info|warning|critical
      message: "Custom message template"

# Execution Settings
parallel: true                      # Run in parallel?
max_workers: 10                     # Max concurrent workers
stop_on_failure: false              # Stop on first failure?
output_format: table                # table|json|yaml|html
```

## Field Reference

### Device Selection

- **Explicit list**: `devices: [R1, R2, R3]`
- **NetBox filter**: `devices.netbox_filter: {role: router, site: DC1}`
- **Regex pattern**: `devices.regex: "^R[0-9]+"`

### Check Task

- `name`: Unique check identifier (required)
- `description`: Human-readable purpose (optional)
- `tool`: Tool to execute (`suzieq_query`, `netconf_get`, `cli_execute`)
- `enabled`: Enable/disable check (default: `true`)
- `parameters`: Tool-specific parameters (dict)

### Threshold Rule

- `field`: Field name to validate (e.g., `count`, `cpu`, `errors`)
- `operator`: Comparison operator (`>`, `<`, `>=`, `<=`, `==`, `!=`)
- `value`: Expected value (int, float, or string)
- `severity`: Alert level (`info`, `warning`, `critical`)
- `message`: Custom violation message (optional, supports templates)

### Message Templates

Use these placeholders in threshold messages:
- `{device}`: Device hostname
- `{field}`: Field name
- `{actual}`: Actual value
- `{value}`: Expected value
- `{operator}`: Comparison operator

Example:
```yaml
message: "Device {device} has {actual} BGP peers (expected {operator} {value})"
# Renders as: "Device R1 has 1 BGP peers (expected >= 2)"
```

## Usage Examples

### 1. Run Single Inspection

```bash
# From config file
uv run python -m olav.cli batch-inspect config/inspections/bgp_peer_audit.yaml

# From Python code
from olav.modes.inspection import run_inspection_mode
from olav.core.llm import LLMFactory

llm = LLMFactory.get_chat_model()
result = await run_inspection_mode(config_path="config/inspections/bgp_peer_audit.yaml")
print(result.to_report(format="table"))
```

### 2. Scheduled Execution (cron)

```bash
# /etc/cron.d/olav-inspections
# Daily BGP audit at 09:00
0 9 * * * olav uv run python -m olav.cli batch-inspect /path/to/bgp_peer_audit.yaml

# Weekly interface check every Monday at 08:00
0 8 * * 1 olav uv run python -m olav.cli batch-inspect /path/to/interface_health.yaml
```

### 3. Custom Inspection

Create `config/inspections/my_custom_check.yaml`:

```yaml
name: vlan_compliance_check
description: Verify VLAN configurations across all switches

devices:
  netbox_filter:
    role: switch
    site: HQ

checks:
  - name: vlan_count_check
    tool: suzieq_query
    parameters:
      table: vlan
      method: summarize
    threshold:
      field: count
      operator: ">="
      value: 5
      severity: warning
      message: "Switch {device} has {actual} VLANs (expected >= {value})"

parallel: true
max_workers: 20
output_format: json
```

## Best Practices

### 1. Version Control
- Commit YAML configs to Git for audit trail
- Use Pull Requests for review before deploying new checks
- Tag releases for production inspections

### 2. Naming Conventions
- Use descriptive names: `bgp_peer_audit.yaml`, not `check1.yaml`
- Include purpose in filename: `daily_core_check.yaml`
- Group related checks: `security_*`, `performance_*`

### 3. Performance Tuning
- Adjust `max_workers` based on device count (10-20 for <100 devices)
- Use `parallel: true` for independent checks
- Enable `stop_on_failure` for critical pre-checks

### 4. Threshold Design
- Start with `severity: info` for new checks, escalate after baselining
- Use `warning` for actionable but non-critical issues
- Reserve `critical` for production-impacting failures

### 5. Testing
- Test new configs on dev devices first: `devices: [DEV-R1]`
- Validate YAML syntax: `yamllint config/inspections/*.yaml`
- Dry-run before scheduling: `uv run python -m olav.cli batch-inspect --dry-run`

## Available Tools

### suzieq_query
SuzieQ parquet data queries (read-only, fast)

**Parameters**:
- `table`: SuzieQ table (`bgp`, `interfaces`, `routes`, `ospf`, etc.)
- `state`: Filter by state (`Established`, `up`, `full`)
- `method`: Query method (`get`, `summarize`, `unique`)

**Example**:
```yaml
tool: suzieq_query
parameters:
  table: bgp
  state: Established
  method: summarize
```

### netconf_get
NETCONF get operations (read-only, slower than SuzieQ)

**Parameters**:
- `xpath`: NETCONF XPath filter
- `device`: Device hostname

**Example**:
```yaml
tool: netconf_get
parameters:
  xpath: /interfaces/interface[name='GigabitEthernet0/0']
```

### cli_execute
CLI command execution via SSH (read-only by default)

**Parameters**:
- `command`: CLI command to execute
- `device`: Device hostname

**Example**:
```yaml
tool: cli_execute
parameters:
  command: "show ip bgp summary"
```

## Output Formats

### Table (default)
Human-readable text table:
```
═══════════════════════════════════════════════════
Batch Inspection Report: bgp_peer_audit
═══════════════════════════════════════════════════
Summary:
  Total Devices: 3
  Passed: 2 ✓
  Failed: 1 ✗
```

### JSON
Machine-readable JSON:
```json
{
  "config_name": "bgp_peer_audit",
  "summary": {
    "total_devices": 3,
    "passed": 2,
    "failed": 1
  },
  "violations": [...]
}
```

### YAML
Structured YAML output:
```yaml
config_name: bgp_peer_audit
summary:
  total_devices: 3
  passed: 2
  failed: 1
violations: []
```

### HTML
Web-friendly HTML report with color-coded results.

## Troubleshooting

### YAML Syntax Errors
```bash
# Validate YAML syntax
yamllint config/inspections/my_check.yaml

# Common issues:
# - Incorrect indentation (use 2 spaces)
# - Missing quotes for strings with special chars
# - Invalid field names (check schema)
```

### Device Resolution Failures
```
Error: No devices matched filter {role: router, site: INVALID}
```
- Verify NetBox filter criteria
- Check device tags and attributes
- Test regex pattern with sample device names

### Tool Execution Errors
```
Error: Tool 'suzieq_query' failed: table 'invalid_table' not found
```
- Verify tool parameters match tool schema
- Check SuzieQ table names: `bgp`, `interfaces`, `routes`, `ospf`, etc.
- Use `suzieq_schema_search` to discover available tables

### Validation Failures
```
Violation: Device R1 has 1 BGP peers (expected >= 2)
```
- Review threshold rules
- Check if expected values are realistic
- Investigate device-specific issues (BGP config, connectivity)

## Support

For questions or issues:
- Check logs: `logs/olav.log`
- Review test examples: `tests/unit/test_batch_strategy.py`
- Consult documentation: `docs/AGENT_ARCHITECTURE_REFACTOR.md`
- GitHub Issues: Create issue with YAML config and error output
