---
id: network-diagnosis
intent: diagnose
complexity: complex
description: "Structured network fault diagnosis, troubleshoot layer-by-layer using TCP/IP model"
examples:
  - "Why is the network not working"
  - "Network is slow, help me troubleshoot"
  - "A site cannot be accessed"
enabled: true
---

# Network Diagnosis

## Applicable Scenarios
- Network connectivity faults
- Performance problem diagnosis
- Intermittent fault troubleshooting
- End-to-end path analysis

## Identification Signals
User questions contain: "not working", "cannot access", "slow", "packet loss", "timeout", "intermittent"

## Execution Strategy

### Phase 1: Problem Definition (5 minutes)
**Goal**: Clarify problem symptoms and scope

1. **Collect Basic Information**
   ```bash
   - Source address/device: ?
   - Target address/device: ?
   - Problem symptoms: (not working/slow/intermittent)
   - Duration: ?
   - Scope: (single user/full site/specific application)
   - Recent changes: (config/device/link)
   ```

2. **Quick Verification**
   ```bash
   # Verify from multiple test points
   ping <target> -c 10

   # Record results
   - Packet loss: ?
   - Latency: ?
   - Jitter: ?
   ```

### Phase 2: Macro Analysis (10 minutes)
**Goal**: Locate fault domain and impact scope

1. **Path Tracing**
   ```bash
   # Use traceroute to locate problem node
   traceroute <target>

   # Analysis:
   # - Which hop starts losing packets/timing out
   # - Is path as expected
   # - Any abnormal routes
   ```

2. **Topology Check**
   ```bash
   # Check critical nodes
   show ip ospf neighbor     # OSPF neighbors
   show ip bgp summary       # BGP neighbors
   show lldp neighbors       # Layer 2 topology

   # Analysis:
   # - Are neighbor relationships normal
   # - Any neighbors down
   # - Any topology changes
   ```

3. **Impact Scope Assessment**
   ```bash
   # Batch ping test
   # - Other hosts in same subnet
   # - Hosts in different subnets
   # - External networks

   # Determine impact scope:
   # - Single host (local issue)
   # - Single subnet (gateway/layer 2 issue)
   # - Multiple subnets (routing/layer 3 issue)
   # - Network-wide (core/exit issue)
   ```

**Output**: Macro analysis report
```
## Macro Analysis Results
- Fault domain: [specific location]
- Impact scope: [impact description]
- Suspected nodes: [device/interface list]
- Preliminary assessment: [physical/layer 2/layer 3 issue]
```

### Phase 3: Micro Analysis (15-30 minutes)
**Goal**: Layer-by-layer troubleshooting within fault domain, identify root cause

#### TCP/IP Layer-by-Layer Troubleshooting Framework

**Layer 1: Physical Layer (5 minutes)**
```bash
# Check items:
show interfaces status
show interfaces counters errors
show interfaces transceiver detail

# Focus metrics:
✓ Interface status: up/up
✓ Error counts: CRC, input errors, output errors
✓ Optical power: RX/TX in normal range
✓ Traffic: input/output rate normal

# Common issues:
✗ Interface down/down
✗ CRC errors increasing
✗ Optical power abnormal
✗ Many runts/giants
```

**Layer 2: Data Link Layer (5 minutes)**
```bash
# Check items:
show vlan brief
show mac address-table
show spanning-tree summary
show lldp neighbors detail

# Focus metrics:
✓ VLAN status: active
✓ MAC table: relevant MACs learned
✓ STP status: forwarding, no loops
✓ LLDP: neighbor discovery normal

# Common issues:
✗ VLAN mismatch
✗ MAC not learned
✗ STP blocked
✗ Layer 2 loop
```

**Layer 3: Network Layer (10 minutes)**
```bash
# Check items:
show ip interface brief
show ip route <target>
show arp
show ip ospf neighbor
show ip bgp summary

# Focus metrics:
✓ Interface IP: configured correctly, status up
✓ Routing table: path to target exists
✓ ARP: target MAC resolved
✓ Routing protocol: neighbors normal, routes converged

# Common issues:
✗ IP configuration error
✗ Missing route
✗ ARP cannot resolve
✗ Routing protocol neighbor down
✗ Route flapping
```

**Layer 4: Transport Layer (5 minutes)**
```bash
# Check items:
show access-lists
show ip nat translations
show control-plane
show running-config | include service

# Focus metrics:
✓ ACL: no blocking rules
✓ NAT: translation normal
✓ Port: service port reachable

# Common issues:
✗ ACL blocking
✗ NAT misconfiguration
✗ Port filtering
```

**Layer 5: Application Layer (optional, depends on business)**
```bash
# Check items:
show ip dns server
show running-config | include service
# Business-specific checks

# Common issues:
✗ DNS resolution failure
✗ Service not running
```

### Phase 4: Root Cause Identification (5 minutes)
**Synthesize analysis, determine root cause**

1. **Elimination Method**
   ```
   ✓ Physical layer normal
   ✓ Layer 2 normal
   ✗ Layer 3 missing route
   → Root cause: Route configuration error/not published
   ```

2. **Correlation Analysis**
   ```
   - Interface CRC errors + low optical power
   → Root cause: Optical module aging

   - OSPF neighbor down + authentication config error
   → Root cause: OSPF authentication password mismatch

   - ACL blocking + specific traffic not working
   → Root cause: ACL rule misconfiguration
   ```

3. **Timeline Analysis**
   ```
   - Fault start time
   - Recent config changes
   - Device reboot/replacement
   → Find triggering event
   ```

### Phase 5: Solution and Verification (10 minutes)

**Develop Solution**
1. **Temporary Mitigation** (if needed)
   ```
   - Switch to backup link
   - Adjust routing policy
   - Temporarily bypass faulty point
   ```

2. **Permanent Fix**
   ```
   - Correct configuration error
   - Replace faulty hardware
   - Optimize network design
   - Add monitoring alerts
   ```

**Verification Steps**
```bash
# 1. Verify config changes
show running-config | section <relevant-config>

# 2. Verify status recovery
show <relevant-status-command>

# 3. Business test
ping <target> -c 100
traceroute <target>

# 4. Continuous monitoring
# Monitor for 10-30 minutes to confirm stability
```

## Common Fault Scenarios and Troubleshooting Paths

### Scenario 1: Single User Cannot Access Network
```
Troubleshooting Path:
1. ping local gateway → check local connection
2. ping public IP → check routing
3. check VLAN/MAC → check layer 2
4. check ACL/NAT → check policies
```

### Scenario 2: Full Subnet Cannot Access
```
Troubleshooting Path:
1. check gateway device → access/distribution layer
2. check VLAN config → SVI status
3. check uplink → core layer
4. check route publishing → routing protocol
```

### Scenario 3: Slow Network
```
Troubleshooting Path:
1. traceroute to locate slow node
2. check error counters/utilization of that node
3. check QoS configuration
4. check path selection
```

### Scenario 4: Intermittent Faults
```
Troubleshooting Path:
1. check interface error counter growth trend
2. check routing protocol stability
3. check STP status changes
4. check link quality
```

### Scenario 5: Specific Application Not Working
```
Troubleshooting Path:
1. test basic connectivity (ping)
2. test port reachability (telnet <ip> <port>)
3. check ACL policy
4. check application layer config
```

## Output Format

### Diagnosis Report Template
```markdown
## Network Fault Diagnosis Report

### Problem Description
[User's description of the problem]

### Macro Analysis
**Path Tracing**: [traceroute result]
**Fault Domain**: [identified fault location]
**Impact Scope**: [impact description]

### Micro Analysis
**Physical Layer**: ✅/❌ [findings]
**Layer 2**: ✅/❌ [findings]
**Layer 3**: ✅/❌ [findings]
**Layer 4**: ✅/❌ [findings]

### Root Cause
[Identified root cause]

### Solution
1. Temporary measures: [if any]
2. Permanent fix: [specific steps]

### Verification Results
✅/❌ [verification result]
```

## Best Practices

### 1. Systematic Troubleshooting
- Follow layer order strictly
- Complete one layer before moving to next
- Record all check results

### 2. Parallel Checks
- Multiple devices can be checked in parallel
- Use batch_query for efficiency
- Unrelated checks can run in parallel

### 3. Comparative Analysis
- Compare with normal devices/links
- Compare with historical data
- Compare with configuration baseline

### 4. Change Control
- Avoid config changes during diagnosis
- Make changes after confirming root cause
- Verify after fixing
- Record all changes

### 5. Documentation
- Record diagnosis process
- Record root cause
- Record solution
- Save to knowledge/solutions/

## Tool Usage Priority

### Prefer Using
1. `smart_query(device, intent)` - Quick information gathering
2. `batch_query(devices, intent)` - Batch checking
3. `list_devices()` - Understand environment

### Use as Needed
4. `search_capabilities(query, platform)` - Find specific commands
5. `nornir_execute(device, command)` - Execute specific commands

### Supporting Tools
- `ping`, `traceroute` - Connectivity testing
- `show` commands - Status checking
- `debug` commands - Deep debugging (use carefully)

## Important Notes

### Safety First
- Only execute read-only commands for diagnosis
- No config changes (unless explicitly requested)
- No dangerous commands (reload, etc.)

### Efficiency Priority
- Prefer batch tools
- Avoid duplicate checks
- Quickly locate fault domain

### User Communication
- Report progress promptly
- Explain technical terms
- Give clear recommendations
- Provide verification methods

## Learning Behavior

After successful diagnosis:
1. **Save case**: `write_file .olav/knowledge/solutions/<problem>.md`
2. **Update skill**: If discovering new patterns, update `skills/network-diagnosis.md`
3. **Update aliases**: If using new device aliases, update `knowledge/aliases.md`
4. **Record tags**: For later retrieval

## Related Skills
- `quick-query.md` - Simple queries
- `deep-analysis.md` - Deep analysis (using macro/micro subagents)
- `device-inspection.md` - Device inspection
