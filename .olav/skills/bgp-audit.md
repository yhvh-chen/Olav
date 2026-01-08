# BGP Audit

## Use Cases
- BGP neighbor state checking
- Route table auditing
- AS path verification
- BGP policy compliance checking

## Recognition Triggers
User questions containing: "BGP", "routing protocol", "AS number", "BGP neighbor", "routing policy"

## Execution Strategy
1. Use `parse_inspection_scope()` to determine BGP device scope
2. Use `nornir_bulk_execute()` to execute BGP check commands in bulk
3. Analyze BGP neighbor status and route table
4. Identify abnormal neighbors and route flapping
5. Use `generate_report()` to generate BGP audit report

## Check Items

### BGP Neighbor Status
- [ ] show ip bgp summary (neighbor summary)
- [ ] show ip bgp neighbors (neighbor detailed info)
- [ ] show ip bgp neighbors | include Idle (check idle neighbors)

### Route Table
- [ ] show ip route bgp (BGP routes)
- [ ] show ip bgp (BGP table)
- [ ] show ip bgp regexp _AS_NUMBER_ (routes from specific AS)

### Path Verification
- [ ] show ip bgp neighbors <peer> advertised-routes (advertised routes)
- [ ] show ip bgp neighbors <peer> received-routes (received routes)
- [ ] traceroute <target> (path verification)

## Report Format
Use `generate_report(template="bgp-audit")` to generate report containing:
- BGP neighbor list and status
- Route statistics
- Abnormal neighbors/routes
- AS path information
- Recommendations

## Anomaly Detection

### Critical Issues
- Neighbor status is Idle or Active
- BGP table entry abnormal growth
- Routes received from wrong AS
- Route flapping

### Alert Thresholds
- Neighbor establishment time < 1 hour → potential instability
- BGP table size > 10,000 entries → check for route leaks
- Abnormal route update rate → check route updates

## Example

### Execute BGP Audit
```
User: "Audit BGP status on all edge routers"

Agent steps:
1. parse_inspection_scope("all edge routers")
   → Based on knowledge base identify role:edge

2. nornir_bulk_execute(
       devices=["R-Edge-1", "R-Edge-2"],
       commands=[
           "show ip bgp summary",
           "show ip bgp neighbors",
           "show ip route bgp | count"
       ],
       max_workers=5
   )

3. Analyze results:
   - Check all BGP neighbors status is Established
   - Count sent/received routes
   - Identify abnormal neighbors
   - Check route table size

4. generate_report(template="bgp-audit", results=results)
```

### Expected Output
```
✅ BGP Audit Complete

Audit Scope: 2 edge routers
Audit Time: 2025-01-08 15:00

BGP Neighbor Summary:
  R-Edge-1:
    ✅ 65001 (ISP1) - Established, 2h15m
    ✅ 65002 (ISP2) - Established, 2h15m
    ✅ 65003 (ISP3) - Established, 2h10m
    Received Routes: 1,250 / Advertised Routes: 450

  R-Edge-2:
    ✅ 65001 (ISP1) - Established, 2h20m
    ✅ 65004 (ISP4) - Established, 2h05m
    ⚠️  65002 (ISP2) - Idle (Connection refused) ← Anomaly
    Received Routes: 1,100 / Advertised Routes: 380

Anomalies:
  ⚠️  R-Edge-2 to ISP2 (65002) neighbor status is Idle
     Possible Causes: Peer connection refused, config error, ACL blocking

Recommendations:
  1. Check network connectivity from R-Edge-2 to ISP2
  2. Verify BGP configuration (neighbor AS, password)
  3. Check firewall/ACL rules
  4. Contact ISP2 to verify their side configuration

Report generated: .olav/reports/bgp-audit-20250108.html
```
