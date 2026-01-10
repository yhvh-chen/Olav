#!/usr/bin/env python3
"""OLAV v0.8 Main Entry Point - Delegates to CLI"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv

load_dotenv()

from olav.cli import main

if __name__ == "__main__":
    main()
