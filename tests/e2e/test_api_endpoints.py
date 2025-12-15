"""Tests for refactored API endpoints."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add src and config to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

@pytest.mark.asyncio
async def test_refactored_endpoints():
    """Test endpoints moved to new routers."""
    from olav.server.app import create_app
    from olav.server.auth import generate_access_token

    app = create_app()
    client = TestClient(app)
    access_token = generate_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}

    # 1. Test /config (monitoring.py)
    response = client.get("/config", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "features" in data

    # 2. Test /autocomplete/devices (autocomplete.py)
    # Note: This might return empty list if no inventory, but should be 200
    response = client.get("/autocomplete/devices?q=test", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "devices" in data
    assert "total" in data

    # 3. Test /autocomplete/tables (autocomplete.py)
    response = client.get("/autocomplete/tables?q=bgp", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "tables" in data
    assert "total" in data
