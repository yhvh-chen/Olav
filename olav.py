#!/usr/bin/env python3
"""OLAV CLI Entry Point.

This is the main entry point for OLAV CLI. It simply imports and runs
the Typer app from src/olav/main.py.

Usage:
    # Normal mode (3 standard workflows)
    uv run olav.py
    uv run olav.py "查询 R1 接口状态"
    
    # Expert mode (enables Deep Dive workflow)
    uv run olav.py -e "审计所有边界路由器 BGP 配置"
    uv run olav.py --expert "跨域故障深度分析"
"""
import sys
from pathlib import Path

# Add src to path to enable olav imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

if __name__ == "__main__":
    from olav.main import app
    app()
