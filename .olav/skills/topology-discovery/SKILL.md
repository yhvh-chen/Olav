---
name: Topology Discovery
description: Discover L1/L3 network topology and visualize device connections
version: 1.0.0

# OLAV Extended Fields
intent: discovery
complexity: medium

# Output Configuration
output:
  format: markdown
  language: auto
  sections:
    - summary
    - details
    - visualization
---

# Topology Discovery - Network Topology Management

## Applicable Scenarios
- Initial network topology discovery
- Network mapping and documentation
- Path analysis between devices
- Neighbor relationship queries
- Network visualization and diagram generation

## Identification Signals
User questions contain: "topology", "network map", "connections", "neighbors", "path between", "discovery", "visualize"

## Execution Strategy

### Discovery Phase
1. **List target devices** using `list_devices()` or use specified devices
2. **Discover topology** using `discover_topology(devices)`
3. **Store results** in DuckDB topology database (automatic)

### Query Phase
1. **Query topology age** using `get_topology_age()`
2. **Query path** using `query_path(source, destination)`
3. **Query neighbors** using `query_neighbors(device, layer)`
4. **Show summary** using `show_topology()`

### Visualization Phase
1. **Generate HTML visualization** using `render_topology_html()`
2. **Visualize path** using `visualize_path(source, destination)`
3. **Visualize site** using `visualize_site(site)`

## Discovery Strategy

### L1 Physical Neighbors
- **Intent**: Get device physical connection relationships
- **Required Data**: Local port, remote device name, remote port
- **Protocols**: CDP (Cisco Discovery Protocol), LLDP (Link Layer Discovery Protocol)

### L3 Routing Neighbors
- **Intent**: Get routing protocol neighbor states
- **Required Data**: Neighbor IP/ID, state, protocol parameters (Area, AS)
- **Protocols**: OSPF (Open Shortest Path First), BGP (Border Gateway Protocol)

## Command Execution Flow

### For Discovery
```
1. discover_topology([devices])
   ├── Get device list from Nornir inventory
   ├── For each device:
   │   ├── Execute L1 discovery (CDP/LLDP commands)
   │   ├── Execute L3 discovery (OSPF/BGP commands)
   │   └── Parse and store in topology.db
   └── Return summary (device count, link count, timestamp)
```

### For Path Query
```
1. query_path(source, destination)
   ├── Load topology from topology.db
   ├── Calculate shortest path using NetworkX
   └── Return path with data age
```

### For Neighbor Query
```
1. query_neighbors(device, [layer])
   ├── Load topology from topology.db
   ├── Filter by device and optional layer
   └── Return neighbors with connection details
```

## Usage Examples

### Discovery
```bash
# Discover all devices
User: "Discover the network topology"
Action: discover_topology()

# Discover specific devices
User: "Discover topology for R1, R2, R3"
Action: discover_topology("R1,R2,R3")

# Refresh specific devices
User: "Refresh topology for R1"
Action: discover_topology("R1")
```

### Query
```bash
# Query path
User: "What's the path from R1 to R5?"
Action: query_path("R1", "R5")
Output: "Path: R1 -> R2 -> R3 -> R5 (Data age: 10 minutes ago)"

# Query neighbors
User: "Who are R1's neighbors?"
Action: query_neighbors("R1")
Output: "R1 neighbors (3): R2 via Gi0/1 (L1/CDP), R3 via Gi0/2 (L1/CDP), ISP via Gi0/0 (L3/BGP) (Data age: 10 minutes ago)"

# Query L1 neighbors only
User: "What are the physical connections to R1?"
Action: query_neighbors("R1", "L1")

# Query topology summary
User: "Show topology summary"
Action: show_topology()
Output: "Topology Summary: 5 devices, 12 links (Data age: 10 minutes ago)"

# Check data age
User: "How old is the topology data?"
Action: get_topology_age()
Output: "10 minutes ago"
```

### Visualization
```bash
# Generate full topology visualization
User: "Visualize the network topology"
Action: render_topology_html()
Output: "data/visualizations/topology/2026-01-12_143052_full.html"

# Visualize path between devices
User: "Show me the path from R1 to R5"
Action: visualize_path("R1", "R5")
Output: "data/visualizations/path/2026-01-12_143500_R1-R5.html"

# Visualize specific site
User: "Visualize the lab site topology"
Action: visualize_site("lab")
Output: "data/visualizations/topology/2026-01-12_150030_site-lab.html"

# Visualize specific devices
User: "Visualize R1, R2, R3"
Action: render_topology_html(devices="R1,R2,R3", description="core-devices")
Output: "data/visualizations/topology/2026-01-12_151000_core-devices.html"
```

## Data Storage

### Topology Database Schema (topology.db)
```sql
-- Devices table
topology_devices (
    name VARCHAR PRIMARY KEY,
    hostname VARCHAR,
    platform VARCHAR,
    mgmt_ip VARCHAR,
    site VARCHAR,
    role VARCHAR,
    discovered_at TIMESTAMP
)

-- Links table (L1/L3 relationships)
topology_links (
    id INTEGER PRIMARY KEY,
    local_device VARCHAR,
    local_port VARCHAR,
    remote_device VARCHAR,
    remote_port VARCHAR,
    layer VARCHAR CHECK (layer IN ('L1', 'L3')),
    protocol VARCHAR,  -- CDP, LLDP, OSPF, BGP
    metadata JSON,
    discovered_at TIMESTAMP,
    UNIQUE(local_device, local_port, remote_device, remote_port, layer)
)
```

## Design Principles

| Principle | Description |
|-----------|-------------|
| **Lightweight** | Minimal dependencies, only NetworkX and pyvis |
| **Transparent** | All data includes timestamps for age awareness |
| **Practical** | Focus on L1/L3, avoid L2 complexity |
| **Direct** | No HITL required, automated macro → micro flow |

## Data Freshness Strategy

### Manual Refresh Only
- `/topology discover` - Full discovery of all devices
- `/topology refresh R1 R2` - Refresh specific devices
- All queries return data + timestamp
- Users/Agents see timestamp and decide refresh need

### No Automatic Refresh
- No automatic refresh decisions
- No background polling
- No stale data detection
- Trust Agent/User judgment

## Query Results Format

### Path Query
```markdown
Path: R1 -> R2 -> R3 -> R5
Hops: 3
Layer: L1 (CDP)
Data age: 10 minutes ago
```

### Neighbor Query
```markdown
R1 Neighbors (3 connections):
├─ R2 via Gi0/1 (L1/CDP)
├─ R3 via Gi0/2 (L1/CDP)
└─ ISP via Gi0/0 (L3/BGP)

Data age: 10 minutes ago
```

### Topology Summary
```markdown
Network Topology Summary
Devices: 15
Links: 42
├─ L1 (Physical): 28 links
└─ L3 (Routing): 14 links

Data age: 10 minutes ago
Last discovery: 2026-01-12 14:30:00
```

## Report Output

### Discovery Report
```
reports/topology-discovery-20260112-143000.md
├─ Discovery Summary
├─ Device Inventory
├─ Link Details (L1 + L3)
├─ Topology Statistics
└─ Visualization Links
```

## Integration with Analyze Skill

### Macro Analysis Phase
- Use cached topology data for initial direction
- Display data age prominently
- Label findings as "preliminary, pending micro validation"

### Micro Analysis Phase
- Execute live commands (show ospf neighbor, etc.)
- Real-time validation of macro topology findings
- Correct preliminary conclusions as needed

### No Code-Layer Validation
- All validation logic in Agent
- Code only provides data + timestamps
- Agent decides refresh/verification needs
