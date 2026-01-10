---
name: batch-query
version: 1.0
type: command
platform: all
description: Query multiple devices with the same intent in parallel
---

# Batch Query Command

Execute the same type of query across multiple devices in parallel. Much faster than querying devices one by one.

## Usage

```
/batch-query <devices> <intent>
```

## Arguments

- **devices**: Comma-separated device names, or "all" for all devices
- **intent**: Query intent (interface, bgp, ospf, route, vlan, mac, version)

## Examples

```
/batch-query "R1,R2,R3" interface
/batch-query "all" version
/batch-query "R1,R2,SW1,SW2" bgp
```

## Implementation

```python
#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv
load_dotenv()


def main():
    """Execute a batch query across multiple devices."""
    parser = argparse.ArgumentParser(
        description="Query multiple devices with the same intent",
        prog="/batch-query"
    )
    parser.add_argument("devices", help="Comma-separated device names or 'all'")
    parser.add_argument("intent", help="Query intent (e.g., 'interface', 'bgp')")
    
    args = parser.parse_args()
    
    try:
        from olav.tools.smart_query import batch_query
        result = batch_query.invoke({
            "devices": args.devices,
            "intent": args.intent,
        })
        print(result)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```
