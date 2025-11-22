"""Benchmark script to compare ReAct vs Legacy agent performance.

Usage:
    uv run python scripts/benchmark_agents.py
    uv run python scripts/benchmark_agents.py --queries 5
    uv run python scripts/benchmark_agents.py --mode react  # Test only ReAct
"""

import asyncio
import time
from typing import Literal

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()

# Test query set (simple → complex)
TEST_QUERIES = [
    # Simple queries (85%) - 1-2 tool calls
    "查询接口状态",
    "有多少台设备在线",
    "显示 BGP 邻居数量",
    "查询 OSPF 状态",
    "列出所有 VLAN",
    
    # Medium queries (10%) - 3-5 tool calls
    "检查是否有接口 Down",
    "分析 BGP 会话健康状况",
    
    # Complex queries (5%) - 5+ tool calls
    "诊断网络中的路由问题",
]


async def run_query(query: str, mode: Literal["react", "legacy"]) -> dict:
    """Run a single query and measure metrics."""
    from olav.main import _run_single_query
    from olav.ui.chat_ui import ChatUI
    
    ui = ChatUI()
    start_time = time.time()
    
    try:
        # Suppress output during benchmark
        import sys
        from io import StringIO
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        # Run query
        await _run_single_query(query, None, mode, ui)
        
        elapsed = time.time() - start_time
        
        # Restore stdout
        sys.stdout = old_stdout
        
        return {
            "query": query,
            "mode": mode,
            "elapsed": elapsed,
            "success": True,
            "error": None,
        }
    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "query": query,
            "mode": mode,
            "elapsed": elapsed,
            "success": False,
            "error": str(e),
        }


@app.command()
def main(
    queries: int = typer.Option(8, "--queries", "-n", help="Number of queries to test (max 8)"),
    mode: str = typer.Option("both", "--mode", "-m", help="Test mode: react, legacy, or both"),
):
    """Run benchmark comparing ReAct vs Legacy agent."""
    console.print(f"\n[bold cyan]OLAV Agent Benchmark[/bold cyan]")
    console.print(f"Testing {queries} queries in {mode} mode(s)\n")
    
    test_queries = TEST_QUERIES[:queries]
    results = []
    
    async def run_benchmarks():
        modes = ["react", "legacy"] if mode == "both" else [mode]
        
        for query in test_queries:
            console.print(f"[yellow]Testing:[/yellow] {query}")
            
            for test_mode in modes:
                console.print(f"  [{test_mode}] Running...", end="")
                result = await run_query(query, test_mode)  # type: ignore
                results.append(result)
                
                status = "[green]✓[/green]" if result["success"] else "[red]✗[/red]"
                console.print(f" {status} {result['elapsed']:.1f}s")
        
        return results
    
    # Run benchmarks
    results = asyncio.run(run_benchmarks())
    
    # Generate report
    console.print("\n[bold cyan]Performance Summary[/bold cyan]\n")
    
    # Create comparison table
    table = Table(title="ReAct vs Legacy Comparison")
    table.add_column("Query", style="cyan")
    table.add_column("ReAct (s)", justify="right", style="green")
    table.add_column("Legacy (s)", justify="right", style="yellow")
    table.add_column("Speedup", justify="right", style="magenta")
    
    if mode == "both":
        react_results = [r for r in results if r["mode"] == "react"]
        legacy_results = [r for r in results if r["mode"] == "legacy"]
        
        for i, query in enumerate(test_queries):
            react_time = react_results[i]["elapsed"] if i < len(react_results) else 0
            legacy_time = legacy_results[i]["elapsed"] if i < len(legacy_results) else 0
            speedup = f"{(1 - react_time / legacy_time) * 100:.1f}%" if legacy_time > 0 else "N/A"
            
            table.add_row(
                query[:40] + "..." if len(query) > 40 else query,
                f"{react_time:.1f}",
                f"{legacy_time:.1f}",
                speedup,
            )
        
        # Add summary row
        react_avg = sum(r["elapsed"] for r in react_results) / len(react_results)
        legacy_avg = sum(r["elapsed"] for r in legacy_results) / len(legacy_results)
        overall_speedup = f"{(1 - react_avg / legacy_avg) * 100:.1f}%"
        
        table.add_row(
            "[bold]Average[/bold]",
            f"[bold]{react_avg:.1f}[/bold]",
            f"[bold]{legacy_avg:.1f}[/bold]",
            f"[bold]{overall_speedup}[/bold]",
        )
    else:
        # Single mode results
        for result in results:
            table.add_row(
                result["query"][:40],
                f"{result['elapsed']:.1f}" if result['mode'] == 'react' else "-",
                f"{result['elapsed']:.1f}" if result['mode'] == 'legacy' else "-",
                "-",
            )
    
    console.print(table)
    
    # Export to markdown
    md_file = "benchmark_results.md"
    with open(md_file, "w", encoding="utf-8") as f:
        f.write("# OLAV Agent Performance Benchmark\n\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## Results\n\n")
        f.write("| Query | ReAct (s) | Legacy (s) | Speedup |\n")
        f.write("|-------|-----------|------------|----------|\n")
        
        if mode == "both":
            react_results = [r for r in results if r["mode"] == "react"]
            legacy_results = [r for r in results if r["mode"] == "legacy"]
            
            for i, query in enumerate(test_queries):
                react_time = react_results[i]["elapsed"]
                legacy_time = legacy_results[i]["elapsed"]
                speedup = f"{(1 - react_time / legacy_time) * 100:.1f}%"
                f.write(f"| {query} | {react_time:.1f} | {legacy_time:.1f} | {speedup} |\n")
            
            react_avg = sum(r["elapsed"] for r in react_results) / len(react_results)
            legacy_avg = sum(r["elapsed"] for r in legacy_results) / len(legacy_results)
            overall_speedup = f"{(1 - react_avg / legacy_avg) * 100:.1f}%"
            f.write(f"| **Average** | **{react_avg:.1f}** | **{legacy_avg:.1f}** | **{overall_speedup}** |\n")
    
    console.print(f"\n[green]Results exported to {md_file}[/green]")


if __name__ == "__main__":
    app()
