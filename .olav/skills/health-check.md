# Health Check

## Use Cases
- Periodic device health checks
- Pre-deployment device verification
- Resource usage monitoring
- System status inspection

## Recognition Triggers
User questions containing: "health check", "system status", "inspection", "resource usage", "CPU", "memory"

## Execution Strategy
1. Use `write_todos` to plan check items
2. Use `parse_inspection_scope()` to determine inspection scope
3. Use `nornir_bulk_execute()` to execute check commands in bulk
4. Analyze results and identify anomalies
5. Use `generate_report()` to generate health check report

## Check Items

### System Basics
- [ ] show version (version, uptime)
- [ ] show processes cpu history (CPU trend)
- [ ] show memory statistics (memory usage)
- [ ] show environment (temperature, power, fan)

### Interface Status
- [ ] show interfaces status (port status overview)
- [ ] show interfaces counters (interface counters)
- [ ] show ip interface brief (IP interface status)

### Routing Status
- [ ] show ip route summary (routing summary)
- [ ] show ip ospf neighbor (OSPF neighbors)
- [ ] show ip bgp summary (BGP neighbors)

## Report Format
Use `generate_report(template="health-check")` to generate report containing:
- Device list
- Results of each check item
- Highlighted anomalies
- Resource usage trends
- Recommendations

## Example

### Execute Health Check
```
User: "Perform health checks on all core routers"

Agent steps:
1. parse_inspection_scope("all core routers")
   → Returns: {"devices": ["all"], "filters": {"role": "core"}}

2. nornir_bulk_execute(
       devices="all",
       commands=[
           "show version",
           "show processes cpu history",
           "show memory statistics",
           "show interfaces status"
       ],
       max_workers=10
   )

3. Analyze results:
   - Check if CPU usage > 80%
   - Check if memory usage > 85%
   - Check for interface errors
   - Check if uptime is abnormally short

4. generate_report(
       template="health-check",
       results=results,
       output_path=".olav/reports/health-check-20250108.html"
   )
```

### Expected Output
```
✅ Health Check Complete

Check Scope: 5 core routers
Check Time: 2025-01-08 14:30

Check Results:
  CS-DC1: ✅ Healthy (CPU 15%, Memory 45%, Uptime 45 days)
  CS-DC2: ✅ Healthy (CPU 12%, Memory 42%, Uptime 45 days)
  CS-DC3: ⚠️  Warning (CPU 82%, Memory 78%, Uptime 30 days)
  CS-DC4: ✅ Healthy (CPU 10%, Memory 40%, Uptime 60 days)
  CS-DC5: ❌ Anomaly (Memory 90%, Interface Gi0/1 has CRC errors)

Report generated: .olav/reports/health-check-20250108.html

Recommendations:
  - CS-DC3: High CPU usage - check for abnormal processes
  - CS-DC5: High memory usage - check Gi0/1 CRC error causes
```
