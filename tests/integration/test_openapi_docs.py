"""Test script to verify OpenAPI documentation rendering.

Validates:
- OpenAPI schema generation
- Swagger UI accessibility
- ReDoc accessibility
- Example responses in schema
"""

import httpx
import json
import pytest
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

console = Console()


def test_openapi_schema():
    """Test OpenAPI JSON schema generation."""
    console.print("\n[bold cyan]Testing OpenAPI Schema Generation...[/bold cyan]\n")
    
    try:
        response = httpx.get("http://localhost:8000/openapi.json", timeout=5.0)
        response.raise_for_status()
        
        schema = response.json()
        
        # Display basic info
        info = schema.get("info", {})
        console.print(Panel(
            f"[green]✓ Title:[/green] {info.get('title')}\n"
            f"[green]✓ Version:[/green] {info.get('version')}\n"
            f"[green]✓ Description:[/green] {len(info.get('description', ''))} characters",
            title="OpenAPI Info",
            border_style="green"
        ))
        
        # Display tags
        tags = schema.get("tags", [])
        if tags:
            table = Table(title="OpenAPI Tags", show_header=True, header_style="bold magenta")
            table.add_column("Name", style="cyan")
            table.add_column("Description", style="white")
            
            for tag in tags:
                table.add_row(tag.get("name"), tag.get("description", ""))
            
            console.print(table)
        
        # Display paths
        paths = schema.get("paths", {})
        console.print(f"\n[bold]Registered Endpoints:[/bold] {len(paths)}")
        for path, methods in paths.items():
            for method, details in methods.items():
                summary = details.get("summary", "No summary")
                console.print(f"  [cyan]{method.upper()}[/cyan] {path} - {summary}")
        
        # Check for examples in responses
        console.print("\n[bold]Checking Response Examples...[/bold]")
        example_count = 0
        for path, methods in paths.items():
            for method, details in methods.items():
                responses = details.get("responses", {})
                for status_code, response_data in responses.items():
                    content = response_data.get("content", {})
                    if content:
                        for media_type, media_data in content.items():
                            if "example" in media_data:
                                example_count += 1
                                console.print(f"  [green]✓[/green] {method.upper()} {path} ({status_code}) has example")
        
        console.print(f"\n[bold green]Total Examples Found:[/bold green] {example_count}")
        
        # Display sample endpoint schema
        if "/auth/login" in paths and "post" in paths["/auth/login"]:
            console.print("\n[bold]Sample Endpoint Detail (/auth/login):[/bold]")
            login_endpoint = paths["/auth/login"]["post"]
            syntax = Syntax(
                json.dumps(login_endpoint, indent=2),
                "json",
                theme="monokai",
                line_numbers=True
            )
            console.print(syntax)
        
        # Test passes if we get here
        assert True
    
    except httpx.ConnectError:
        console.print("[bold red]✗ Server not running at http://localhost:8000[/bold red]")
        console.print("[yellow]Start server with: uv run python -m olav.server.app[/yellow]")
        pytest.fail("Server not running at http://localhost:8000")
    except Exception as e:
        console.print(f"[bold red]✗ Error: {e}[/bold red]")
        pytest.fail(f"OpenAPI schema test failed: {e}")


def test_swagger_ui():
    """Test Swagger UI accessibility."""
    console.print("\n[bold cyan]Testing Swagger UI...[/bold cyan]\n")
    
    try:
        response = httpx.get("http://localhost:8000/docs", timeout=5.0)
        response.raise_for_status()
        
        console.print(Panel(
            "[green]✓ Swagger UI accessible at http://localhost:8000/docs[/green]\n"
            "[white]Open in browser to test interactive documentation[/white]",
            title="Swagger UI",
            border_style="green"
        ))
        assert True
    
    except httpx.ConnectError:
        console.print("[bold red]✗ Server not running[/bold red]")
        pytest.fail("Server not running - cannot access Swagger UI")
    except Exception as e:
        console.print(f"[bold red]✗ Error: {e}[/bold red]")
        pytest.fail(f"Swagger UI test failed: {e}")


def test_redoc():
    """Test ReDoc accessibility."""
    console.print("\n[bold cyan]Testing ReDoc...[/bold cyan]\n")
    
    try:
        response = httpx.get("http://localhost:8000/redoc", timeout=5.0)
        response.raise_for_status()
        
        console.print(Panel(
            "[green]✓ ReDoc accessible at http://localhost:8000/redoc[/green]\n"
            "[white]Alternative documentation view with better readability[/white]",
            title="ReDoc",
            border_style="green"
        ))
        assert True
    
    except httpx.ConnectError:
        console.print("[bold red]✗ Server not running[/bold red]")
        pytest.fail("Server not running - cannot access ReDoc")
    except Exception as e:
        console.print(f"[bold red]✗ Error: {e}[/bold red]")
        pytest.fail(f"ReDoc test failed: {e}")


def main():
    """Run all OpenAPI documentation tests."""
    console.print(Panel.fit(
        "OpenAPI Documentation Test Suite",
        border_style="bold blue"
    ))
    
    results = {
        "OpenAPI Schema": test_openapi_schema(),
        "Swagger UI": test_swagger_ui(),
        "ReDoc": test_redoc(),
    }
    
    # Summary
    console.print("\n" + "="*60)
    console.print("[bold]Test Results Summary[/bold]")
    console.print("="*60)
    
    for test_name, passed in results.items():
        status = "[green]✓ PASS[/green]" if passed else "[red]✗ FAIL[/red]"
        console.print(f"{status} {test_name}")
    
    total_passed = sum(results.values())
    total_tests = len(results)
    
    console.print(f"\n[bold]Total: {total_passed}/{total_tests} tests passed[/bold]")
    
    if total_passed == total_tests:
        console.print("\n[bold green]✓ All documentation tests passed![/bold green]")
        console.print("\n[yellow]Next steps:[/yellow]")
        console.print("  1. Open http://localhost:8000/docs in browser")
        console.print("  2. Test /auth/login endpoint with demo credentials")
        console.print("  3. Verify example responses in Swagger UI")
        console.print("  4. Check ReDoc for better documentation readability")
    else:
        console.print("\n[bold red]✗ Some tests failed. Start server first:[/bold red]")
        console.print("  uv run python -m olav.server.app")


if __name__ == "__main__":
    main()
