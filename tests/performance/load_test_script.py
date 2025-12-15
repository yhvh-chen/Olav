"""
OLAV Performance Load Test Script

This script simulates concurrent users interacting with the OLAV API to measure:
- Throughput (Requests Per Second)
- Latency (P50, P95, P99)
- Error Rate

Usage:
    uv run python tests/performance/load_test_script.py
"""

import asyncio
import time
import statistics
import os
import httpx
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

console = Console()

# Configuration
SERVER_URL = os.getenv("OLAV_SERVER_URL", "http://localhost:18001")
API_TOKEN = os.getenv("OLAV_API_TOKEN", "")
CONCURRENT_USERS = 20
TOTAL_REQUESTS = 200  # Total requests to send across all users
TIMEOUT = 30.0

# Test Queries (Mix of simple and complex)
QUERIES = [
    "check R1 BGP status",
    "show interface Gi0/1 on Switch-A",
    "what is the uptime of R2",
    "list all devices in site Beijing",
    "check system health"
]

class LoadTester:
    def __init__(self):
        self.results = []
        self.errors = 0
        self.headers = {}
        if API_TOKEN:
            self.headers["Authorization"] = f"Bearer {API_TOKEN}"

    async def send_request(self, client: httpx.AsyncClient, query: str):
        start_time = time.time()
        try:
            # Using the /invoke endpoint for LangServe or a custom chat endpoint
            # Adjust endpoint based on actual API structure. Assuming /api/v1/chat or similar
            # Based on previous context, it might be /invoke or similar. 
            # Let's try the standard LangServe invoke endpoint for the root agent if known, 
            # or the chat endpoint used by the CLI.
            # CLI uses: /invoke (implied from LangServe RemoteRunnable)
            
            # We'll target a specific workflow or the root orchestrator
            # Assuming the root orchestrator is exposed at /
            
            payload = {
                "input": {
                    "messages": [
                        {"role": "user", "content": query}
                    ]
                },
                "config": {},
                "kwargs": {}
            }
            
            # Note: LangServe endpoints usually follow /<runnable>/invoke
            # We will try to hit the health check first to ensure connectivity, 
            # then try a simple query if possible, or just measure health check for baseline if auth fails.
            # Actually, let's try to hit the 'query_diagnostic' workflow directly if exposed, 
            # or the root agent.
            
            # For this test, we'll use a simpler endpoint to test raw throughput first: /health
            # Then we can try a real query.
            
            # Let's do a mix: 50% health (baseline), 50% query (processing)
            if "health" in query:
                resp = await client.get(f"{SERVER_URL}/health", timeout=TIMEOUT)
            else:
                # Assuming root agent is at /invoke
                resp = await client.post(
                    f"{SERVER_URL}/invoke", 
                    json=payload, 
                    headers=self.headers,
                    timeout=TIMEOUT
                )
            
            resp.raise_for_status()
            duration = (time.time() - start_time) * 1000 # ms
            return duration, resp.status_code
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            # console.print(f"[red]Error: {e}[/red]")
            return duration, 0

    async def user_session(self, user_id: int, requests_per_user: int, progress):
        async with httpx.AsyncClient() as client:
            for i in range(requests_per_user):
                query = QUERIES[i % len(QUERIES)]
                # Use health check for now to test infrastructure throughput without LLM cost/latency
                # unless we want to test LLM. Let's stick to health for infrastructure baseline.
                # To test full stack, we need the LLM.
                # Let's use /health for safety in this initial script to avoid spamming LLM API.
                # We can toggle this.
                
                target = "health" # "query"
                
                duration, status = await self.send_request(client, target)
                
                if status == 200:
                    self.results.append(duration)
                else:
                    self.errors += 1
                    
                progress.advance(task_id)

    async def run(self):
        console.print(f"[bold cyan]Starting Load Test[/bold cyan]")
        console.print(f"Server: {SERVER_URL}")
        console.print(f"Users: {CONCURRENT_USERS}")
        console.print(f"Total Requests: {TOTAL_REQUESTS}")
        
        start_time = time.time()
        
        requests_per_user = TOTAL_REQUESTS // CONCURRENT_USERS
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        ) as progress:
            global task_id
            task_id = progress.add_task("[cyan]Sending requests...", total=TOTAL_REQUESTS)
            
            tasks = [
                self.user_session(i, requests_per_user, progress) 
                for i in range(CONCURRENT_USERS)
            ]
            await asyncio.gather(*tasks)

        total_time = time.time() - start_time
        self.report(total_time)

    def report(self, total_time):
        if not self.results:
            console.print("[bold red]No successful requests recorded.[/bold red]")
            return

        avg_latency = statistics.mean(self.results)
        p50 = statistics.median(self.results)
        p95 = statistics.quantiles(self.results, n=20)[18] if len(self.results) >= 20 else p50
        p99 = statistics.quantiles(self.results, n=100)[98] if len(self.results) >= 100 else p95
        rps = len(self.results) / total_time

        table = Table(title="Load Test Results (Baseline /health)")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Requests", str(TOTAL_REQUESTS))
        table.add_row("Successful", str(len(self.results)))
        table.add_row("Failed", str(self.errors))
        table.add_row("Total Time", f"{total_time:.2f}s")
        table.add_row("RPS (Throughput)", f"{rps:.2f} req/s")
        table.add_row("Avg Latency", f"{avg_latency:.2f} ms")
        table.add_row("P50 Latency", f"{p50:.2f} ms")
        table.add_row("P95 Latency", f"{p95:.2f} ms")
        table.add_row("P99 Latency", f"{p99:.2f} ms")

        console.print(table)

if __name__ == "__main__":
    tester = LoadTester()
    asyncio.run(tester.run())
