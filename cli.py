#!/usr/bin/env python3
"""OLAV CLI Entry Point (cli.py).

This is the main entry point for OLAV CLI v2 - Thin Client Architecture.

The CLI connects to the OLAV API server via HTTP/SSE and provides:
- Interactive REPL mode with history and auto-completion
- Streaming responses with real-time thinking visualization
- HITL approval flow for write operations
- Inspection and document management commands

Usage:
    # Interactive REPL mode
    uv run cli.py
    
    # Single query
    uv run cli.py query "Query R1 BGP status"
    
    # Expert mode
    uv run cli.py query -m expert "Audit all border routers"
    
    # Inspection commands
    uv run cli.py inspect list
    uv run cli.py inspect run daily-check
    
    # Document management
    uv run cli.py doc list
    uv run cli.py doc search "BGP configuration"
    
Environment Variables:
    OLAV_SERVER_URL: API server URL (default: http://localhost:8000)
    OLAV_TIMEOUT: Request timeout in seconds (default: 300)
"""
import sys
from pathlib import Path

# Add src to path to enable olav imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

if __name__ == "__main__":
    from olav.cli.commands import app
    app()
