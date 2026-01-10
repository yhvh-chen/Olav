"""OLAV CLI - Entry point for olav package when run as module"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Load environment first
from dotenv import load_dotenv

load_dotenv()

from olav.cli import main

if __name__ == "__main__":
    main()
