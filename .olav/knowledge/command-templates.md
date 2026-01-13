# Command Templates Guide

## Overview

Some commands require parameters to be filled in before execution. These are marked with `!VARIABLE_NAME` placeholders in the command templates.

## How to Use Templates

When you encounter a command template like:
```
show interface !INTERFACE_NAME
```

You must replace `!INTERFACE_NAME` with an actual interface name:
```
show interface GigabitEthernet0/1
show interface Ethernet0/0
show interface Vlan10
```

## Common Variables

| Variable | Description | Examples |
|----------|-------------|----------|
| `!INTERFACE_NAME` | Interface identifier | `GigabitEthernet0/1`, `Ethernet0/0`, `Vlan10` |
| `!VLAN_ID` | VLAN number | `10`, `100`, `999` |
| `!PREFIX` | IP prefix with mask | `10.0.0.0/8`, `192.168.1.0/24` |
| `!IP_ADDRESS` | Single IP address | `10.1.1.1`, `192.168.1.100` |
| `!MAC_ADDRESS` | MAC address | `aabb.cc00.1100`, `0000.5e00.0101` |
| `!NEIGHBOR_IP` | BGP/OSPF neighbor IP | `10.1.1.2`, `172.16.0.1` |
| `!AS_NUMBER` | BGP AS number | `65000`, `65001`, `64512` |
| `!VRF_NAME` | VRF name | `management`, `customer-a` |
| `!ACL_NAME` | Access-list name | `inside-acl`, `permit-list` |
| `!ROUTE_MAP_NAME` | Route-map name | `RM-PREFER`, `RM-DENY` |
| `!TARGET` | Ping/traceroute target | `8.8.8.8`, `google.com` |

## Examples

### Query Specific Interface
```
User: "Check R1's Gi0/1 status"

Template: show interface !INTERFACE_NAME
Command:  show interface GigabitEthernet0/1
```

### Check BGP Neighbor
```
User: "Show BGP routes from 10.1.1.2"

Template: show ip bgp neighbors !NEIGHBOR_IP advertised-routes
Command:  show ip bgp neighbors 10.1.1.2 advertised-routes
```

### Find MAC Address
```
User: "Where is MAC aabb.cc00.1100?"

Template: show mac address-table address !MAC_ADDRESS
Command:  show mac address-table address aabb.cc00.1100
```

## Important Rules

1. **Always replace variables** - Never send `!VARIABLE_NAME` to the device
2. **Match the format** - Use correct interface naming (full or abbreviated as device accepts)
3. **Validate first** - If unsure of the value, query first:
   - `show ip interface brief` → get interface names
   - `show vlan brief` → get VLAN IDs
   - `show ip bgp summary` → get neighbor IPs

## Template File Location

Templates are defined in:
```
.olav/imports/commands/cisco_ios_templates.txt
```
