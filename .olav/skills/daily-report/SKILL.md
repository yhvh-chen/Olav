---
name: Daily Report
description: Global analysis and report generation (Reduce phase)
version: 1.0.0
intent: report
mode: reduce
---

## Daily Report - Report Generation Phase

### Input Data (Summarized, not raw)

- inspect_summary.json: Device inspection summary (with anomaly summary)
- log_summary.json: Device event summary
- topology_path: reports/topology.html (linked reference)

### Analysis Tasks

#### 1. Issue Summary
Count devices with anomalies and classify by type

#### 2. Correlation Analysis
Cross-device and cross-type correlation:
- High CPU + OSPF DOWN → Route instability
- CRC errors + BGP reset → Physical layer issue
- Multiple device alerts → Possible network event

#### 3. Priority Ranking
- CRITICAL: Affects business operations
- WARNING: Requires attention
- INFO: Informational only

#### 4. Report Generation

### Report Template

```markdown
# Network Daily Report - {{date}}

## 📊 Executive Summary

| Metric | Value | Status |
|--------|-------|--------|
| Total Devices | {{count}} | {{status}} |
| Devices with Anomalies | {{anomaly_count}} | {{anomaly_status}} |
| Check Items Pass Rate | {{ok_rate}}% | {{ok_status}} |

## 🗺️ Network Topology

[View Full Topology](./topology.html)

## 🔴 Issues Requiring Attention

### 1. {{title}} (CRITICAL)

**Symptoms**: {{symptom}}

**Root Cause**: {{root_cause}}

**Impact**: {{impact}}

**Recommendation**: {{recommendation}}

---

<details>
<summary>Detailed Data</summary>

### Inspection Results

{{detailed_checks}}

### Event Details

{{detailed_events}}

</details>
```

### Correlation Analysis Guidelines

#### Common Correlation Patterns

| Pattern | Correlation | Explanation |
|---------|-------------|-------------|
| Route Instability | High CPU + OSPF DOWN | CPU overload causes routing calculation delay |
| Physical Layer Issue | CRC errors + BGP reset | Link quality issue causes BGP session reset |
| Network Event | Multiple device alerts | Possible network partition or core device failure |
| Thermal Issue | High temp + Fan failure | Cooling system failure, immediate action needed |
| Memory Leak | Persistent memory growth + Performance degradation | Possible software bug, device restart needed |

#### Priority Determination

- **CRITICAL (Immediate action)**:
  - Device restart/downtime
  - Core link down
  - All OSPF/BGP neighbors lost
  - Severe temperature/fan failure

- **WARNING (Monitor)**:
  - Single OSPF/BGP neighbor issue
  - High CPU/memory utilization
  - Interface flapping
  - Single non-critical port down

- **INFO (Record)**:
  - Configuration change
  - Planned maintenance
  - Recovered temporary anomaly

### Output Requirements

1. **Generate report in English**
2. **Executive Summary** must include:
   - Total device count
   - Count and percentage of devices with anomalies
   - Check item statistics (normal/warning/critical)
3. **Issue list** sorted by priority
4. **Each issue** must include:
   - Symptom description (what was observed)
   - Root cause analysis (why it happened)
   - Impact assessment (effect on business)
   - Action recommendation (what to do)
5. **Reference topology diagram** for problem localization
6. **Detailed data** in collapsible sections
