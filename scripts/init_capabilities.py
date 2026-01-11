#!/usr/bin/env python
"""Check and initialize OLAV capabilities database."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv()

from olav.core.database import get_database

db = get_database()

try:
    result = db.conn.execute('SELECT COUNT(*) as count FROM capabilities').fetchall()
    count = result[0][0]
    print(f"Capabilities count: {count}")
    if count == 0:
        raise Exception("Capabilities table is empty")
except Exception:
    print("Initializing capabilities from whitelist files...")

    # Load whitelist files
    whitelist_dir = Path(".olav/imports/commands")
    if whitelist_dir.exists():
        for platform_file in whitelist_dir.glob("*.txt"):
            platform = platform_file.stem
            print(f"\nLoading {platform} commands from {platform_file}...")

            commands = []
            for line in platform_file.read_text().split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    commands.append(line)

            print(f"Found {len(commands)} commands for {platform}")

            # Load into database
            count = 0
            for cmd in commands:
                try:
                    db.insert_capability(
                        cap_type="command",
                        platform=platform,
                        name=cmd,
                        source_file=str(platform_file),
                        is_write=False
                    )
                    count += 1
                except Exception as add_err:
                    print(f"Warning: Could not add '{cmd}': {add_err}")

            print(f"Successfully loaded {count}/{len(commands)} commands")

    # Check again
    result = db.conn.execute('SELECT COUNT(*) as count FROM capabilities').fetchall()
    print(f"\nTotal capabilities after initialization: {result[0][0]}")
