---
name: search-capabilities
version: 1.0
type: command
platform: all
description: Search available network commands from capabilities database
---

# Search Capabilities Command

Search the capabilities database to find available network commands and APIs by keyword, platform, or type.

## Usage

```
/search-capabilities <query> [--platform <platform>] [--type <type>] [--limit <limit>]
```

## Arguments

- **query**: Search query (e.g., 'interface', 'bgp', 'ospf')

## Options

- **--platform, -p**: Filter by platform (cisco_ios, huawei_vrp, etc.)
- **--type, -t**: Filter by type ('command' or 'api')
- **--limit, -l**: Maximum results to return (default: 10)

## Examples

```
/search-capabilities interface
/search-capabilities bgp --platform cisco_ios
/search-capabilities ospf --type command
/search-capabilities vlan --platform cisco_ios --type command
/search-capabilities route --limit 20
```

## Implementation

```python
#!/usr/bin/env python3
import sys
import json
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv
load_dotenv()


def main():
    """Search capabilities database."""
    parser = argparse.ArgumentParser(
        description="Search available network commands",
        prog="/search-capabilities"
    )
    parser.add_argument("query", help="Search query (e.g., 'interface', 'bgp')")
    parser.add_argument("--platform", "-p", help="Filter by platform (e.g., 'cisco_ios')")
    parser.add_argument("--type", "-t", dest="cap_type", help="Filter by type ('command' or 'api')")
    parser.add_argument("--limit", "-l", type=int, default=10, help="Maximum results (default: 10)")
    
    args = parser.parse_args()
    
    try:
        from olav.tools.capabilities import search_capabilities
        result = search_capabilities.invoke({
            "query": args.query,
            "platform": args.platform,
            "cap_type": args.cap_type,
            "limit": args.limit,
        })
        print(result)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```
