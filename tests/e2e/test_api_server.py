"""Smoke test for OLAV API Server (LangServe).

Usage:
    pytest tests/e2e/test_api_server.py -v
"""

import asyncio
import sys
from pathlib import Path

import pytest

# Add src and config to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))  # For config module


@pytest.mark.asyncio
async def test_server_startup():
    """Test FastAPI server startup and basic endpoints."""
    from olav.server.app import create_app
    from olav.server.auth import generate_access_token

    app = create_app()
    
    # Generate access token for tests
    access_token = generate_access_token()

    # Test health check endpoint
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # 1. Testing /health endpoint (no auth)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data

    # 2. Testing /me endpoint (requires auth)
    me_response = client.get("/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_response.status_code == 200
    user_data = me_response.json()
    assert user_data["username"] == "admin"

    # 3. Testing unauthorized access (401 with www-authenticate header)
    unauth_response = client.get("/status")
    assert unauth_response.status_code == 401  # No auth header - should return 401

    # 4. Testing /status endpoint (with auth)
    status_response = client.get("/status", headers={"Authorization": f"Bearer {access_token}"})
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert "health" in status_data
    assert "user" in status_data

    # 5. Checking OpenAPI documentation
    docs_response = client.get("/docs")
    assert docs_response.status_code == 200
    redoc_response = client.get("/redoc")
    assert redoc_response.status_code == 200
