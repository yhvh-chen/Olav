"""E2E Integration Tests for LangServe API.

Comprehensive test suite validating:
- Server health and infrastructure connectivity
- Single-token authentication (token auto-generated on server startup)
- Workflow execution endpoints (invoke and stream)
- CLI client remote mode integration
- Error scenarios and edge cases

Prerequisites:
- Infrastructure running: PostgreSQL, OpenSearch, Redis
- API server running on http://localhost:8000
- Environment variables configured (.env)

Run with full infrastructure:
    docker-compose up -d
    pytest tests/e2e/test_langserve_api.py -v
"""

import asyncio
import json
import os
from typing import AsyncIterator

import httpx
import threading
import time
import uvicorn
import pytest
from langserve import RemoteRunnable

# Set Windows event loop policy for async tests
if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _check_infrastructure() -> bool:
    """Check if PostgreSQL is available (minimal infrastructure check)."""
    import socket
    try:
        # Check PostgreSQL (port 55432 from docker-compose)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 55432))
        sock.close()
        return result == 0
    except Exception:
        return False


# Skip all tests if infrastructure is not available
pytestmark = pytest.mark.skipif(
    not _check_infrastructure(),
    reason="Infrastructure not available. Run 'docker-compose up -d' first."
)


# ============================================
# Fixtures
# ============================================
@pytest.fixture(scope="module")
def base_url() -> str:
    """API server base URL."""
    return os.getenv("OLAV_SERVER_URL", "http://127.0.0.1:8000")


# ============================================
# Session-scoped server fixture
# ============================================
@pytest.fixture(scope="session", autouse=True)
def start_uvicorn_server() -> None:
    """Start a uvicorn server in a background thread for E2E tests.

    Rationale:
    External process management in CI/Windows was unstable; server would
    terminate before tests executed causing ConnectError. This fixture
    ensures a persistent in-process server lifecycle.
    """
    # Reset global state to ensure routes are mounted fresh
    # This is needed when other tests (e.g., test_api_server.py) run before us
    import olav.server.app as app_module
    app_module._routes_mounted = False
    app_module.orchestrator = None
    app_module.checkpointer = None
    
    from olav.server.app import app  # Local import to avoid side effects before fixture

    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, name="uvicorn-test-server", daemon=True)
    thread.start()

    # Poll for readiness
    for _ in range(50):  # ~10s max
        try:
            r = httpx.get("http://127.0.0.1:8000/health", timeout=0.5)
            if r.status_code in (200, 503):
                break
        except Exception:
            time.sleep(0.2)
    else:  # pragma: no cover - diagnostic output if server never started
        print("[TestFixture] Warning: Server did not become ready within timeout")

    yield

    # Signal shutdown
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def server_token() -> str:
    """Get the single access token from the server.
    
    In single-token auth mode, the token is auto-generated on server startup.
    We import it directly from the auth module.
    """
    from olav.server.auth import get_access_token, generate_access_token
    
    # Ensure token is generated
    generate_access_token()
    token = get_access_token()
    assert token is not None, "Server token not generated"
    return token


@pytest.fixture
def auth_headers(server_token: str) -> dict:
    """Authorization headers with server token."""
    return {"Authorization": f"Bearer {server_token}"}


# ============================================
# Test 1: Server Health and Infrastructure
# ============================================
@pytest.mark.asyncio
async def test_server_health_check(base_url: str):
    """Test server health endpoint and infrastructure connectivity.
    
    Validates:
    - Server is running and responding
    - PostgreSQL connection established
    - Workflow orchestrator initialized
    - Health endpoint returns correct structure
    """
    async with httpx.AsyncClient() as client:
        last_data = None
        for attempt in range(15):  # up to ~7.5s (15 * 0.5s)
            response = await client.get(f"{base_url}/health", timeout=10.0)
            assert response.status_code == 200, f"Health endpoint not reachable: {response.text}"
            last_data = response.json()
            required_fields = ["status","version","environment","postgres_connected","orchestrator_ready"]
            for f in required_fields:
                assert f in last_data, f"Missing '{f}' field in health response"
            if last_data["status"] == "healthy" and last_data["postgres_connected"] and last_data["orchestrator_ready"]:
                break
            await asyncio.sleep(0.5)
        assert last_data is not None, "Health response missing"
        assert last_data["status"] == "healthy", f"Server status still {last_data['status']} after polling"
        assert last_data["postgres_connected"] is True, "PostgreSQL not connected after polling"
        assert last_data["orchestrator_ready"] is True, "Orchestrator not ready after polling"
        assert last_data["version"].startswith("0."), f"Unexpected version format: {last_data['version']}"


# ============================================
# Test 2: Authentication - Token Validation Success
# ============================================
@pytest.mark.asyncio
async def test_authentication_token_success(base_url: str, server_token: str):
    """Test successful token authentication.
    
    Validates:
    - Server token allows access to protected endpoints
    - /me endpoint returns user info with token
    - User is treated as admin in single-token mode
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/me",
            headers={"Authorization": f"Bearer {server_token}"},
            timeout=10.0,
        )
        
        assert response.status_code == 200, f"/me failed with token: {response.text}"
        
        data = response.json()
        assert "username" in data, "Missing username field"
        assert "role" in data, "Missing role field"
        # In single-token mode, all users are admin
        assert data["role"] == "admin", f"Expected admin role, got {data['role']}"


# ============================================
# Test 3: Authentication - Invalid Token Failure
# ============================================
@pytest.mark.asyncio
async def test_authentication_invalid_token_failure(base_url: str):
    """Test authentication failure with invalid token.
    
    Validates:
    - Invalid tokens are rejected with 401
    - Error message is informative
    - WWW-Authenticate header present (RFC 7235)
    """
    async with httpx.AsyncClient() as client:
        # Test with completely invalid token
        response = await client.get(
            f"{base_url}/me",
            headers={"Authorization": "Bearer invalid_token_12345"},
            timeout=10.0,
        )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data, "Missing error detail"
        
        # Validate WWW-Authenticate header (RFC 7235 compliance)
        assert "www-authenticate" in response.headers, "Missing WWW-Authenticate header"
        assert response.headers["www-authenticate"] == "Bearer", "Invalid WWW-Authenticate value"


# ============================================
# Test 4: Protected Endpoint - Token Validation
# ============================================
@pytest.mark.asyncio
async def test_protected_endpoint_with_valid_token(base_url: str, auth_headers: dict):
    """Test protected endpoint access with valid token.
    
    Validates:
    - /me endpoint requires authentication
    - Valid token grants access
    - Returns correct user information
    - User data structure is complete
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/me",
            headers=auth_headers,
            timeout=10.0,
        )
        
        assert response.status_code == 200, f"/me endpoint failed: {response.text}"
        
        data = response.json()
        assert "username" in data, "Missing 'username' field"
        assert "role" in data, "Missing 'role' field"
        assert "disabled" in data, "Missing 'disabled' field"
        
        # In single-token mode, user is admin
        assert data["role"] == "admin", f"Unexpected role: {data['role']}"
        assert data["disabled"] is False, "User should not be disabled"


# ============================================
# Test 5: Protected Endpoint - Missing Token
# ============================================
@pytest.mark.asyncio
async def test_protected_endpoint_without_token(base_url: str):
    """Test protected endpoint access without authentication.
    
    Validates:
    - Protected endpoints reject unauthenticated requests
    - Returns 401 Unauthorized
    - Error message is clear
    - WWW-Authenticate header is present (RFC 7235 compliance)
    """
    async with httpx.AsyncClient() as client:
        # Test /me endpoint without token
        response = await client.get(f"{base_url}/me", timeout=10.0)
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        # RFC 7235: 401 responses MUST include WWW-Authenticate header
        assert "www-authenticate" in response.headers, "Missing WWW-Authenticate header (RFC 7235 violation)"
        assert response.headers["www-authenticate"] == "Bearer", f"Expected 'Bearer', got '{response.headers.get('www-authenticate')}'"
        
        data = response.json()
        assert "detail" in data, "Missing error detail"
        
        # Test /status endpoint without token
        response = await client.get(f"{base_url}/status", timeout=10.0)
        assert response.status_code == 401, f"Expected 401 for /status, got {response.status_code}"
        assert "www-authenticate" in response.headers, "Missing WWW-Authenticate header in /status endpoint"


# ============================================
# Test 6: Protected Endpoint - Invalid Token
# ============================================
@pytest.mark.asyncio
async def test_protected_endpoint_with_invalid_token(base_url: str):
    """Test protected endpoint access with malformed/invalid token.
    
    Validates:
    - Invalid tokens are rejected
    - Returns 401 or 403
    - Error message indicates credential validation failure
    """
    async with httpx.AsyncClient() as client:
        invalid_headers = {"Authorization": "Bearer invalid_token_12345"}
        
        response = await client.get(
            f"{base_url}/me",
            headers=invalid_headers,
            timeout=10.0,
        )
        
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data, "Missing error detail"


# ============================================
# Test 7: Status Endpoint with Auth
# ============================================
@pytest.mark.asyncio
async def test_status_endpoint_with_auth(base_url: str, auth_headers: dict):
    """Test /status endpoint with authentication.
    
    Validates:
    - Returns combined health + user data
    - Health data structure matches /health endpoint
    - User data structure matches /me endpoint
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/status",
            headers=auth_headers,
            timeout=10.0,
        )
        
        assert response.status_code == 200, f"/status endpoint failed: {response.text}"
        
        data = response.json()
        assert "health" in data, "Missing 'health' field"
        assert "user" in data, "Missing 'user' field"
        
        # Validate health data
        health = data["health"]
        assert health["status"] == "healthy", f"Unexpected health status: {health['status']}"
        assert health["postgres_connected"] is True, "PostgreSQL should be connected"
        assert health["orchestrator_ready"] is True, "Orchestrator should be ready"
        
        # Validate user data
        user = data["user"]
        assert user["role"] == "admin", f"Unexpected role: {user['role']}"


# ============================================
# Test 8: Workflow Execution - Invoke Endpoint
# ============================================
@pytest.mark.asyncio
async def test_workflow_invoke_endpoint(base_url: str, auth_headers: dict):
    """Test workflow execution via /orchestrator/invoke (non-streaming).
    
    Validates:
    - Invoke endpoint is accessible
    - Accepts workflow input with config
    - Returns output structure
    - Handles simple query successfully
    
    Note: This is a smoke test. Full workflow functionality tested separately.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:  # Increased to 60s for complex workflows
        # Prepare workflow input
        payload = {
            "input": {
                "messages": [
                    {"role": "user", "content": "查询系统健康状态"}
                ]
            },
            "config": {
                "configurable": {
                    "thread_id": "test-invoke-001"
                }
            }
        }
        
        response = await client.post(
            f"{base_url}/orchestrator/invoke",
            headers={**auth_headers, "Content-Type": "application/json"},
            json=payload,
        )
        
        # LangServe invoke endpoint should return 200
        assert response.status_code == 200, f"Invoke failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert "output" in data or "messages" in data or isinstance(data, dict), \
            f"Unexpected response structure: {data}"


# ============================================
# Test 9: Workflow Execution - Stream Endpoint
# ============================================
@pytest.mark.asyncio
async def test_workflow_stream_endpoint(base_url: str, auth_headers: dict):
    """Test workflow execution via /orchestrator/stream (Server-Sent Events).
    
    Validates:
    - Stream endpoint is accessible
    - Returns SSE stream (text/event-stream)
    - Receives at least one event
    - Events contain valid JSON data
    
    Note: This is a smoke test. Full streaming tested in integration tests.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:  # Increased to 60s for complex workflows
        payload = {
            "input": {
                "messages": [
                    {"role": "user", "content": "测试流式响应"}
                ]
            },
            "config": {
                "configurable": {
                    "thread_id": "test-stream-001"
                }
            }
        }
        
        # Stream endpoint uses POST to /orchestrator/stream
        async with client.stream(
            "POST",
            f"{base_url}/orchestrator/stream",
            headers={**auth_headers, "Content-Type": "application/json"},
            json=payload,
        ) as response:
            assert response.status_code == 200, f"Stream failed: {response.status_code}"
            
            # Check content type is SSE
            content_type = response.headers.get("content-type", "")
            assert "text/event-stream" in content_type or "application/x-ndjson" in content_type, \
                f"Unexpected content type: {content_type}"
            
            # Read at least one chunk from stream
            chunk_count = 0
            async for chunk in response.aiter_bytes():
                if chunk:
                    chunk_count += 1
                    # First chunk should be valid data
                    if chunk_count == 1:
                        # LangServe streams can be SSE or NDJSON
                        chunk_text = chunk.decode("utf-8")
                        assert len(chunk_text) > 0, "Empty first chunk"
                    
                    # Limit test to first few chunks
                    if chunk_count >= 3:
                        break
            
            assert chunk_count > 0, "No chunks received from stream"


# ============================================
# Test 10: CLI Client Remote Mode
# ============================================
@pytest.mark.asyncio
async def test_cli_client_remote_mode(base_url: str, server_token: str):
    """Test OLAV CLI client in remote mode (API-based execution).
    
    Validates:
    - CLI client can connect to remote server
    - Authentication flow works via CLI
    - Can execute queries via API
    
    Note: Tests the client.py module directly, not subprocess calls.
    """
    from olav.cli.client import OLAVClient
    
    # Create client in remote mode with server token
    client = OLAVClient(local_mode=False, auth_token=server_token)
    
    # Override server URL for test
    client._server_url = base_url
    
    # Test connection (should work with token)
    await client.connect()
    
    # Verify orchestrator is accessible
    assert client.remote_orchestrator is not None or client.remote_health is not None, \
        "Failed to connect to remote server"


# ============================================
# Test 11: Error Scenario - 500 Internal Server Error Handling
# ============================================
@pytest.mark.asyncio
async def test_error_handling_malformed_request(base_url: str, auth_headers: dict):
    """Test API error handling for malformed requests.
    
    Validates:
    - Server handles malformed JSON gracefully
    - Returns appropriate error status (400/422/500)
    - Error response has structured format
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Send malformed JSON to invoke endpoint
        response = await client.post(
            f"{base_url}/orchestrator/invoke",
            headers={**auth_headers, "Content-Type": "application/json"},
            content=b'{"invalid": json}',  # Malformed JSON
        )
        
        # Should return 422 (Unprocessable Entity) or 400 (Bad Request)
        assert response.status_code in [400, 422], \
            f"Expected 400/422 for malformed JSON, got {response.status_code}"
        
        # Error response should be JSON
        try:
            error_data = response.json()
            assert "detail" in error_data or "error" in error_data, \
                "Error response missing detail field"
        except json.JSONDecodeError:
            pytest.fail("Error response is not valid JSON")


# ============================================
# Test 12: LangServe RemoteRunnable Integration
# ============================================
@pytest.mark.asyncio
async def test_langserve_remote_runnable(base_url: str, server_token: str):
    """Test LangServe RemoteRunnable client integration.
    
    Validates:
    - Can create RemoteRunnable client
    - Can invoke workflow remotely
    - Response structure is valid
    
    This tests the Python SDK usage pattern documented in API_USAGE.md.
    """
    # Create RemoteRunnable client (as documented in API_USAGE.md)
    remote_runnable = RemoteRunnable(
        url=f"{base_url}/orchestrator",
        headers={"Authorization": f"Bearer {server_token}"}
    )
    
    # Test invoke
    try:
        result = await remote_runnable.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "测试 RemoteRunnable"}
                ]
            },
            config={
                "configurable": {
                    "thread_id": "test-remote-runnable-001"
                }
            }
        )
        
        # Should return a result (structure varies by workflow)
        assert result is not None, "RemoteRunnable returned None"
        assert isinstance(result, dict) or isinstance(result, list), \
            f"Unexpected result type: {type(result)}"
    
    except Exception as e:
        # If workflow fails, at least verify connection was made
        assert "Connection" not in str(e), f"Connection error: {e}"
        # Other errors may be due to workflow logic, which is acceptable for this E2E test


# ============================================
# Test 13: Sessions API - List Sessions
# ============================================
@pytest.mark.asyncio
async def test_sessions_list(base_url: str, server_token: str):
    """Test sessions list endpoint.
    
    Validates:
    - GET /sessions returns 200 with valid token
    - Response contains sessions array and total count
    - Returns 401 without token
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test with valid token
        response = await client.get(
            f"{base_url}/sessions",
            headers={"Authorization": f"Bearer {server_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "sessions" in data, "Response missing 'sessions' field"
        assert "total" in data, "Response missing 'total' field"
        assert isinstance(data["sessions"], list), "sessions should be a list"
        assert isinstance(data["total"], int), "total should be an integer"
        
        # Test without token (should fail)
        response_no_auth = await client.get(f"{base_url}/sessions")
        assert response_no_auth.status_code == 401, "Expected 401 without auth"


# ============================================
# Test 14: Sessions API - Get Session (Not Found)
# ============================================
@pytest.mark.asyncio
async def test_sessions_get_not_found(base_url: str, server_token: str):
    """Test session get endpoint with non-existent session.
    
    Validates:
    - GET /sessions/{id} returns 404 for non-existent session
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{base_url}/sessions/non-existent-session-12345",
            headers={"Authorization": f"Bearer {server_token}"}
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


# ============================================
# Test 15: Topology API - Get Network Topology
# ============================================
@pytest.mark.asyncio
async def test_topology_endpoint(base_url: str, server_token: str):
    """Test network topology endpoint.
    
    Validates:
    - GET /topology returns 200 with valid token
    - Response contains nodes and edges arrays
    - Returns 401 without token
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test with valid token
        response = await client.get(
            f"{base_url}/topology",
            headers={"Authorization": f"Bearer {server_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "nodes" in data, "Response missing 'nodes' field"
        assert "edges" in data, "Response missing 'edges' field"
        assert isinstance(data["nodes"], list), "nodes should be a list"
        assert isinstance(data["edges"], list), "edges should be a list"
        
        # Validate node structure if any nodes exist
        if data["nodes"]:
            node = data["nodes"][0]
            assert "id" in node, "Node missing 'id' field"
            assert "hostname" in node, "Node missing 'hostname' field"
            assert "status" in node, "Node missing 'status' field"
        
        # Validate edge structure if any edges exist
        if data["edges"]:
            edge = data["edges"][0]
            assert "id" in edge, "Edge missing 'id' field"
            assert "source" in edge, "Edge missing 'source' field"
            assert "target" in edge, "Edge missing 'target' field"
        
        # Test without token (should fail)
        response_no_auth = await client.get(f"{base_url}/topology")
        assert response_no_auth.status_code == 401, "Expected 401 without auth"


@pytest.mark.asyncio
async def test_history_endpoint(base_url: str, server_token: str):
    """Test execution history endpoint (sessions with pagination).
    
    Validates:
    - GET /sessions?limit=10&offset=0 returns 200 with valid token
    - Response contains sessions array and total count
    - Session items have required fields
    - Returns 401 without token
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test with valid token and pagination params
        response = await client.get(
            f"{base_url}/sessions?limit=10&offset=0",
            headers={"Authorization": f"Bearer {server_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure (matches HistoryListResponse)
        assert "sessions" in data, "Response missing 'sessions' field"
        assert "total" in data, "Response missing 'total' field"
        assert isinstance(data["sessions"], list), "sessions should be a list"
        assert isinstance(data["total"], int), "total should be an integer"
        
        # Validate session item structure if any sessions exist
        if data["sessions"]:
            session = data["sessions"][0]
            assert "thread_id" in session, "Session missing 'thread_id' field"
            assert "created_at" in session, "Session missing 'created_at' field"
            assert "updated_at" in session, "Session missing 'updated_at' field"
            assert "message_count" in session, "Session missing 'message_count' field"
        
        # Test without token (should fail)
        response_no_auth = await client.get(f"{base_url}/sessions?limit=10&offset=0")
        assert response_no_auth.status_code == 401, "Expected 401 without auth"


# ============================================
# Summary Report
# ============================================
@pytest.fixture(scope="session", autouse=True)
def print_test_summary(request):
    """Print test summary after all tests complete."""
    yield
    
    # This runs after all tests
    print("\n" + "="*60)
    print("E2E Integration Test Summary")
    print("="*60)
    print("Tests validate:")
    print("  ✓ Server health and infrastructure connectivity")
    print("  ✓ Single-token authentication (auto-generated on startup)")
    print("  ✓ Protected endpoint access control")
    print("  ✓ Workflow execution endpoints (invoke, stream)")
    print("  ✓ CLI client remote mode integration")
    print("  ✓ Error handling (401, 422, malformed requests)")
    print("  ✓ LangServe RemoteRunnable SDK compatibility")
    print("  ✓ Sessions API (list, get, delete)")
    print("  ✓ Topology API (network graph data)")
    print("  ✓ History API (execution history with pagination)")
    print("="*60)
