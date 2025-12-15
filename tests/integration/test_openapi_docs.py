"""Test script to verify OpenAPI documentation rendering.

Validates:
- OpenAPI schema generation
- Swagger UI accessibility
- ReDoc accessibility
- Example responses in schema
"""

import json
import pytest
from fastapi.testclient import TestClient
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

# Import the app directly
from olav.server.app import app

console = Console()

@pytest.fixture
def client():
    """Create a TestClient instance."""
    return TestClient(app)

def test_openapi_schema(client):
    """Test OpenAPI JSON schema generation."""
    console.print("\n[bold cyan]Testing OpenAPI Schema Generation...[/bold cyan]\n")

    response = client.get("/openapi.json")
    assert response.status_code == 200
    
    schema = response.json()

    # Display basic info
    info = schema.get("info", {})
    console.print(Panel(
        f"[green] Title:[/green] {info.get('title')}\n"
        f"[green] Version:[/green] {info.get('version')}\n"
        f"[green] Description:[/green] {len(info.get('description', ''))} characters",
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
                    for _media_type, media_data in content.items():
                        if "example" in media_data:
                            example_count += 1
                            console.print(f"  [green][/green] {method.upper()} {path} ({status_code}) has example")

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

def test_swagger_ui(client):
    """Test Swagger UI accessibility."""
    console.print("\n[bold cyan]Testing Swagger UI...[/bold cyan]\n")

    response = client.get("/docs")
    assert response.status_code == 200

    console.print(Panel(
        "[green] Swagger UI accessible at /docs[/green]\n"
        "[white]Open in browser to test interactive documentation[/white]",
        title="Swagger UI",
        border_style="green"
    ))

def test_redoc(client):
    """Test ReDoc accessibility."""
    console.print("\n[bold cyan]Testing ReDoc...[/bold cyan]\n")

    response = client.get("/redoc")
    assert response.status_code == 200

    console.print(Panel(
        "[green] ReDoc accessible at /redoc[/green]\n"
        "[white]Alternative documentation view with better readability[/white]",
        title="ReDoc",
        border_style="green"
    ))
