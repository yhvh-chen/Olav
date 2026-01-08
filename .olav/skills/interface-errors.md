# Interface Errors

## Use Cases
- Interface error rate anomalies
- CRC error diagnosis
- Packet loss troubleshooting
- Physical layer fault analysis

## Recognition Triggers
User questions containing: "interface errors", "CRC", "packet loss", "error", "dropped packets", "physical layer"

## Execution Strategy
1. Use `parse_inspection_scope()` to determine check scope
2. Use `nornir_bulk_execute()` to execute interface check commands in bulk
3. Analyze error counters, CRC, packet loss
4. Identify problem interfaces and causes
5. Use `generate_report()` to generate interface error report

## Check Items

### Interface Status
- [ ] show interfaces status (interface status)
- [ ] show interfaces counters errors (error counters)
- [ ] show interfaces counters (detailed counters)

### Physical Layer
- [ ] show interfaces transceiver detail (transceiver details)
- [ ] show controllers <interface> (controller info)
- [ ] show logging | include interface (interface-related logs)

### Traffic Statistics
- [ ] show interfaces <interface> (interface details)
- [ ] show traffic interface <interface> (traffic statistics)

## Report Format
Use `generate_report(template="interface-errors")` to generate report containing:
- Interface list and error statistics
- CRC error interfaces
- High packet loss interfaces
- Abnormal transceiver status
- Root cause analysis
- Recommendations

## Anomaly Detection

### Key Metrics
- CRC errors > 100 → physical layer issue
- Input errors > 1000 → check link quality
- Output errors > 1000 → check local config
- Packet loss rate > 1% → network congestion or errors
- Interface flapping (frequent up/down) → check physical connection

### Common Causes
- CRC errors: Transceiver aging, dirty fiber, excessive distance
- Input errors: Peer device issues, poor link quality
- Output errors: Local config error, insufficient resources
- Flapping: Loose cable, config conflict, STP issues

## Example

### Execute Interface Error Analysis
```
User: "Analyze interface errors on all core routers"

Agent steps:
1. parse_inspection_scope("all core routers")

2. nornir_bulk_execute(
       devices=["CS-DC1", "CS-DC2", "CS-DC3"],
       commands=[
           "show interfaces status",
           "show interfaces counters errors",
           "show interfaces transceiver detail"
       ],
       max_workers=5
   )

3. Analyze results:
   - Extract CRC and input/output errors from all interfaces
   - Identify high error rate interfaces
   - Check transceiver status
   - Correlate interface status

4. generate_report(template="interface-errors", results=results)
```

### Expected Output
```
✅ Interface Error Analysis Complete

Analysis Scope: 3 core routers
Analysis Time: 2025-01-08 16:00

Interface Error Summary:
  CS-DC1:
    ✅ Gi0/1-48: Healthy (no errors)
    ✅ Te0/1-4: Healthy (no errors)

  CS-DC2:
    ✅ Gi0/1-48: Healthy (no errors)
    ⚠️  Te0/2: CRC Errors 1,523 ← Anomaly
       Rx Power: -18.5 dBm (low)
       Recommendation: Replace transceiver or check fiber connection

  CS-DC3:
    ⚠️  Gi0/24: Input errors 2,340, CRC errors 856
       Status: up, but errors increasing
       Recommendation: Check peer device and physical link

Anomalous Interfaces:
  1. CS-DC2 Te0/2 - CRC Errors
     Error Type: CRC
     Error Count: 1,523
     Likely Cause: Low transceiver TX power (-18.5 dBm)
     Recommendation: Replace transceiver

  2. CS-DC3 Gi0/24 - Input/CRC Errors
     Error Type: Input errors, CRC
     Error Count: 2,340 / 856
     Likely Cause: Poor link quality, peer device issues
     Recommendation: Check physical connection, check peer device interface

Report generated: .olav/reports/interface-errors-20250108.html
```
