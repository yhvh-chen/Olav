# Device Aliases

Agent should consult this file before executing commands to convert user-provided aliases to actual device names, IPs, or interfaces.

## Instructions
- When user mentions these aliases, automatically replace them with actual values
- Supports multiple types: device names, IP addresses, interface names, VLANs, etc.
- If user uses a new alias, ask for clarification and then update this file

## Alias Table

| Alias | Actual Value | Type | Platform | Notes |
|-------|--------------|------|----------|-------|
| R1 | 192.168.100.101 | device | cisco_ios | border@lab |
| 边界路由器1 | R1 | device | cisco_ios | alias for R1 |
| R1路由器 | R1 | device | cisco_ios | alias for R1 |
| R2 | 192.168.100.102 | device | cisco_ios | border@lab |
| 边界路由器2 | R2 | device | cisco_ios | alias for R2 |
| R2路由器 | R2 | device | cisco_ios | alias for R2 |
| R3 | 192.168.100.103 | device | cisco_ios | core@lab |
| 核心路由器1 | R3 | device | cisco_ios | alias for R3 |
| R3路由器 | R3 | device | cisco_ios | alias for R3 |
| R4 | 192.168.100.104 | device | cisco_ios | core@lab |
| 核心路由器2 | R4 | device | cisco_ios | alias for R4 |
| R4路由器 | R4 | device | cisco_ios | alias for R4 |
| SW1 | 192.168.100.105 | device | cisco_ios | access@lab |
| 接入交换机1 | SW1 | device | cisco_ios | alias for SW1 |
| SW1交换机 | SW1 | device | cisco_ios | alias for SW1 |
| SW2 | 192.168.100.106 | device | cisco_ios | access@lab |
| 接入交换机2 | SW2 | device | cisco_ios | alias for SW2 |
| SW2交换机 | SW2 | device | cisco_ios | alias for SW2 |

## Usage Examples

### Example 1: Device Alias
User: "Check R1 CPU usage"
Agent Parsing:
- Alias: "R1" → 192.168.100.101
- Execute: nornir_execute("R1", "show processes cpu")

### Example 2: Natural Language
User: "Check the border router status"
Agent Parsing:
- Alias: "border-router-1" → R1
- Execute: nornir_execute("R1", "show version")

## Notes
- Aliases are auto-generated from hosts.yaml during init
- Agent can learn new aliases during conversations
- Run `uv run python scripts/init.py --force` to regenerate from hosts.yaml
