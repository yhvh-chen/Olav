#!/usr/bin/env python
"""Force reinitialize OLAV capabilities database."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv()

from olav.core.database import get_database

db = get_database()

# Force reinitialize - clear and reload
print("Clearing existing command capabilities...")
db.conn.execute("DELETE FROM capabilities WHERE type='command'")
db.conn.commit()

whitelist_dir = Path(".olav/imports/commands")
total_count = 0

for platform_file in whitelist_dir.glob("*.txt"):
    if platform_file.name == "blacklist.txt":
        continue

    platform = platform_file.stem
    count = 0

    for line in platform_file.read_text().splitlines():
        line = line.strip()
        # Skip empty lines, comments, and write commands (!)
        if line and not line.startswith("#") and not line.startswith("!"):
            try:
                db.insert_capability(
                    cap_type="command",
                    platform=platform,
                    name=line,
                    source_file=str(platform_file),
                    is_write=False
                )
                count += 1
            except Exception:
                pass  # Skip duplicates

    print(f"Loaded {count} commands for {platform}")
    total_count += count

print(f"\nTotal commands loaded: {total_count}")

# Verify
result = db.search_capabilities("interface", cap_type="command", platform="cisco_ios")
print(f"\nVerification - Interface commands for cisco_ios: {len(result)}")
for r in result[:5]:
    print(f"  - {r['name']}")
