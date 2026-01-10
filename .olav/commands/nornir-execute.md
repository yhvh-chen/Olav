---
name: nornir-execute
version: 1.0
type: command
platform: all
description: Execute network commands via Nornir on network devices
---

# Nornir Execute Command

Execute network commands on devices via Nornir. Commands must be in the whitelist and dangerous commands are automatically blocked for safety.

## Usage

```
/nornir-execute <device> <command>
```

## Arguments

- **device**: Target device name from inventory (e.g., 'R1', 'SW1')
- **command**: CLI command to execute (e.g., 'show version', 'show vlan brief')

## Security

- Commands must be in the whitelist
- Dangerous commands are automatically blocked
- Blacklist includes configuration-changing commands

## Examples

```
/nornir-execute R1 "show version"
/nornir-execute SW1 "show vlan brief"
/nornir-execute R2 "show ip interface brief"
/nornir-execute R1 "show ip route bgp"
```

## Implementation

```python
#!/usr/bin/env python3
import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv
load_dotenv()


def main():
    """Execute a network command on a device."""
    if len(sys.argv) < 3:
        print("Usage: /nornir-execute <device> <command>")
        print("\nExamples:")
        print('  /nornir-execute R1 "show version"')
        print('  /nornir-execute SW1 "show vlan brief"')
        return 1
    
    device = sys.argv[1]
    command = sys.argv[2]
    
    try:
        from olav.tools.network import nornir_execute
        result = nornir_execute.invoke({"device": device, "command": command})
        print(result)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```
