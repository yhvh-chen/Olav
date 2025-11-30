"""Simplified E2E tests for API infrastructure.

Tests basic API functionality without requiring orchestrator initialization.
Useful for validating API server, authentication, and basic endpoints.

NOTE: These tests require the API server to be running.
Run with: OLAV_SERVER_URL=http://localhost:8000 pytest tests/e2e/test_api_basic.py
"""

import asyncio
import os

import httpx
import pytest

# Set Windows event loop policy
if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# Get server URL from environment variable (for Docker compatibility)
BASE_URL = os.getenv("OLAV_SERVER_URL", "http://localhost:8000")


def _server_available() -> bool:
    """Check if server is available."""
    import socket
    try:
        host = BASE_URL.replace("http://", "").replace("https://", "").split(":")[0]
        port = int(BASE_URL.split(":")[-1].split("/")[0]) if ":" in BASE_URL else 8000
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def _get_token_from_server() -> str | None:
    """Get valid token from running server.
    
    In simplified auth mode, the server generates a token on startup.
    For tests, we generate a new token using the auth module directly.
    """
    try:
        from olav.server.auth import generate_access_token, get_access_token
        # If token already generated (e.g., by running server), use it
        existing = get_access_token()
        if existing:
            return existing
        # Otherwise generate new one for tests
        return generate_access_token()
    except Exception:
        return None


# Skip all tests if server is not available
pytestmark = pytest.mark.skipif(
    not _server_available(),
    reason=f"API server not available at {BASE_URL}. Start server first or set OLAV_SERVER_URL."
)


@pytest.fixture
def access_token():
    """Get access token for authenticated requests."""
    token = _get_token_from_server()
    if not token:
        pytest.skip("Could not obtain access token")
    return token


@pytest.mark.asyncio
async def test_health_check():
    """Test basic health check endpoint."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/health", timeout=10.0)
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data


@pytest.mark.asyncio
async def test_me_endpoint_with_auth(access_token):
    """Test /me endpoint with valid token."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "admin"
        assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_me_endpoint_without_auth():
    """Test /me endpoint without token."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/me")
        # FastAPI returns 401 Unauthorized when credentials are not provided
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_status_endpoint(access_token):
    """Test /status endpoint with auth."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/status",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "health" in data
        assert "user" in data


@pytest.mark.asyncio
async def test_config_endpoint():
    """Test /config public endpoint (no auth required)."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/config", timeout=10.0)
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert "features" in data
        assert "workflows" in data
