# Device Aliases

Agent should consult this file before executing commands to convert user-provided aliases to actual device names, IPs, or interfaces.

## Instructions
- When user mentions these aliases, automatically replace them with actual values
- Supports multiple types: device names, IP addresses, interface names, VLANs, etc.
- If user uses a new alias, ask for clarification and then update this file

## Alias Table

| Alias | Actual Value | Type | Platform | Notes |
|-------|--------------|------|----------|-------|
| Core Switches | sw1, sw2 | device | cisco_ios | Core layer switches |
| SW1 | 192.168.100.105 | device | cisco_ios | Core Switch 1 |
| SW2 | 192.168.100.106 | device | cisco_ios | Core Switch 2 |
| Core Routers | r1, r2 | device | cisco_ios | Core layer routers |
| R1 | 192.168.100.101 | device | cisco_ios | Area 1 Core Router |
| R2 | 192.168.100.102 | device | cisco_ios | Area 1 Border Router |
| R3 | 192.168.100.103 | device | cisco_ios | Core Router |
| R4 | 192.168.100.104 | device | cisco_ios | Core Router |
| Border Routers | r3, r4 | device | cisco_ios | Border layer routers |
| Main Link | ethernet0/0, ethernet0/1 | interface | - | Main link interface |
| Management Interface | ethernet0/3 | interface | - | Management network interface |
| Loopback Interface | loopback0 | interface | - | Loopback address interface |
| Office Network | VLAN 10 | vlan | - | Office area |
| Production Network | VLAN 20 | vlan | - | Production area |
| Guest Network | VLAN 30 | vlan | - | Guest area |

## Usage Examples

### Example 1: Device Alias
User: "Check core switch CPU usage"
Agent Parsing:
- Alias: "Core Switches" → 10.1.1.1
- Execute: nornir_execute("10.1.1.1", "show processes cpu")

### Example 2: Interface Alias
User: "Shanghai dedicated line status"
Agent Parsing:
- Device: R1 (10.1.1.1)
- Interface: "Shanghai dedicated line" → GigabitEthernet0/0/1
- Execute: nornir_execute("10.1.1.1", "show interface GigabitEthernet0/0/1")

### Example 3: VLAN Alias
User: "How many users in office network"
Agent Parsing:
- VLAN: "Office Network" → VLAN 100
- Execute: nornir_execute("10.1.1.1", "show vlan brief | include 100")

## Extension Rules

### Learning New Aliases
When user first mentions an unknown alias:
1. Ask: "Which device/interface is 'XX'?"
2. After user clarifies, update this file
3. Confirm type: device, interface, vlan, etc

### Multi-Device Aliases
A group of devices can be represented as a list:
| Alias | Actual Value | Type | Platform |
|-------|--------------|------|----------|
| Core Devices | R1, R2, CS1, CS2 | device_list | cisco_ios |

### Geographic Location Aliases
| Alias | Actual Value | Type | Notes |
|-------|--------------|------|-------|
| Shanghai | site:shanghai | site | Shanghai Branch |
| Beijing | site:beijing | site | Beijing Branch |

## Notes
- Aliases should be clear and concise
- Avoid confusing aliases
- Periodically clean up unused aliases
- Keep in sync with actual network environment

| 核心路由器 | R3, R4 | device | cisco_ios | core@lab |

| 核心路由器 | R3,R4 | device | cisco_ios |  |

| 核心路由器 | R3,R4 | device | cisco_ios | core@lab |

| 核心路由器 | R3,R4 | device | cisco_ios |  |

| 核心路由器 | R3,R4 | device | cisco_ios |  |
