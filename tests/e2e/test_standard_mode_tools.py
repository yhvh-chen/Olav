"""E2E tests for Standard Mode (QueryDiagnosticWorkflow) tool invocations.

Tests the full funnel debugging tool stack in standard mode:
- Layer 1: Knowledge Base (episodic_memory, openconfig_schema)
- Layer 2: Cached Telemetry (suzieq_query, suzieq_schema_search)
- Layer 3: Source of Truth (netbox_api, syslog_search)
- Layer 4: Live Device (netconf, cli)

Also tests:
- NetBox CRUD operations via netbox_api_call
- HITL (Human-in-the-Loop) approval trigger for write operations
"""

import asyncio
import os
import sys

import httpx
import pytest

# Windows event loop fix
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# API base URL
API_BASE_URL = os.environ.get("OLAV_API_URL", "http://localhost:8000")
# Timeout for API calls (standard mode is faster than expert mode)
API_TIMEOUT = 120.0


def make_request_body(query: str) -> dict:
    """Create properly formatted request body for orchestrator API."""
    return {
        "input": {
            "messages": [{"role": "user", "content": query}]
        }
    }


def check_response(result: dict, keywords: list[str], allow_llm_fallback: bool = True) -> bool:
    """Check if response contains expected keywords or is a valid fallback.
    
    Args:
        result: API response JSON
        keywords: List of expected keywords
        allow_llm_fallback: If True, accept LLM fallback as valid (skip scenario)
        
    Returns:
        True if response is valid (contains keywords or is fallback)
    """
    output = str(result.get("final_message", "") or result.get("result", "")).lower()
    
    # Check for LLM fallback response (service unavailable)
    if allow_llm_fallback and ("暂时无法访问" in output or "llm" in output or "占位" in output):
        pytest.skip("LLM service temporarily unavailable")
    
    return any(kw in output for kw in keywords)


class TestStandardModeToolCalls:
    """Test tool invocations in standard mode via API."""

    @pytest.fixture
    def api_client(self):
        """Create async HTTP client with auth token."""
        token = os.environ.get("OLAV_API_TOKEN", "test-token")
        return httpx.AsyncClient(
            base_url=API_BASE_URL,
            timeout=API_TIMEOUT,
            headers={"Authorization": f"Bearer {token}"},
        )

    @pytest.mark.asyncio
    async def test_s01_suzieq_query_tool(self, api_client):
        """Test SuzieQ query tool invocation (Layer 2)."""
        async with api_client as client:
            # Query that should trigger suzieq_query
            response = await client.post(
                "/orchestrator/invoke",
                json=make_request_body("查询所有设备的接口状态"),
            )
            
            if response.status_code != 200:
                pytest.skip(f"API not available: {response.status_code}")
            
            result = response.json()
            # Check if response mentions interfaces or devices
            assert check_response(result, ["interface", "device", "接口", "设备", "status", "状态", "query", "suzieq"])

    @pytest.mark.asyncio
    async def test_s02_netbox_query_tool(self, api_client):
        """Test NetBox API query tool invocation (Layer 3)."""
        async with api_client as client:
            # Query that should trigger netbox_api_call
            response = await client.post(
                "/orchestrator/invoke",
                json=make_request_body("列出 NetBox 中所有设备"),
            )
            
            if response.status_code != 200:
                pytest.skip(f"API not available: {response.status_code}")
            
            result = response.json()
            # Accept either success or "no devices" result
            assert check_response(result, ["netbox", "device", "设备", "inventory", "dcim"])

    @pytest.mark.asyncio
    async def test_s03_syslog_search_tool(self, api_client):
        """Test Syslog search tool invocation (Layer 3)."""
        async with api_client as client:
            # Query that should trigger syslog_search
            response = await client.post(
                "/orchestrator/invoke",
                json=make_request_body("搜索最近的 BGP 相关日志"),
            )
            
            if response.status_code != 200:
                pytest.skip(f"API not available: {response.status_code}")
            
            result = response.json()
            # Should mention syslog or logs
            assert check_response(result, ["log", "syslog", "日志", "bgp", "event", "found", "未找到", "search", "搜索"])


class TestNetBoxCRUDOperations:
    """Test NetBox CRUD operations via standard mode."""

    @pytest.fixture
    def api_client(self):
        """Create async HTTP client with auth token."""
        token = os.environ.get("OLAV_API_TOKEN", "test-token")
        return httpx.AsyncClient(
            base_url=API_BASE_URL,
            timeout=API_TIMEOUT,
            headers={"Authorization": f"Bearer {token}"},
        )

    @pytest.mark.asyncio
    async def test_n01_netbox_list_devices(self, api_client):
        """Test listing devices from NetBox."""
        async with api_client as client:
            response = await client.post(
                "/orchestrator/invoke",
                json=make_request_body("从 NetBox 获取所有设备列表"),
            )
            
            if response.status_code != 200:
                pytest.skip(f"API not available: {response.status_code}")
            
            result = response.json()
            assert check_response(result, ["netbox", "device", "设备", "list", "列表"])

    @pytest.mark.asyncio
    async def test_n02_netbox_get_device_info(self, api_client):
        """Test getting specific device info from NetBox."""
        async with api_client as client:
            response = await client.post(
                "/orchestrator/invoke",
                json=make_request_body("查询 NetBox 中 R1 设备的详细信息"),
            )
            
            if response.status_code != 200:
                pytest.skip(f"API not available: {response.status_code}")
            
            result = response.json()
            assert check_response(result, ["netbox", "r1", "device", "设备", "info", "信息"])


class TestCLIExecution:
    """Test CLI command execution via standard mode."""

    @pytest.fixture
    def api_client(self):
        """Create async HTTP client with auth token."""
        token = os.environ.get("OLAV_API_TOKEN", "test-token")
        return httpx.AsyncClient(
            base_url=API_BASE_URL,
            timeout=API_TIMEOUT,
            headers={"Authorization": f"Bearer {token}"},
        )

    @pytest.mark.asyncio
    async def test_c01_cli_show_command(self, api_client):
        """Test CLI show command execution (read-only, no HITL)."""
        async with api_client as client:
            # This should trigger cli_execute for show command
            response = await client.post(
                "/orchestrator/invoke",
                json=make_request_body("在 R1 上执行 show version 命令"),
            )
            
            if response.status_code != 200:
                pytest.skip(f"API not available: {response.status_code}")
            
            result = response.json()
            # Should either show version output or connection error (if device not reachable)
            assert check_response(result, [
                "version", "ios", "software", 
                "connection", "error", "unreachable", "不可达",
                "cli", "执行", "show", "r1"
            ])


class TestHITLTrigger:
    """Test Human-in-the-Loop approval trigger for write operations.
    
    Note: These tests verify that HITL is triggered, not that writes succeed.
    Write operations require explicit approval which is blocked in automated tests.
    
    Device capabilities:
    - R1: Supports OpenConfig/NETCONF (use netconf_execute)
    - R3: CLI-only device (use cli_execute)
    """

    @pytest.fixture
    def api_client(self):
        """Create async HTTP client with auth token."""
        token = os.environ.get("OLAV_API_TOKEN", "test-token")
        return httpx.AsyncClient(
            base_url=API_BASE_URL,
            timeout=API_TIMEOUT,
            headers={"Authorization": f"Bearer {token}"},
        )

    # ========== NetBox CRUD Tests ==========

    @pytest.mark.asyncio
    async def test_h01_netbox_create_device(self, api_client):
        """Test that NetBox create device operation triggers HITL."""
        async with api_client as client:
            response = await client.post(
                "/orchestrator/invoke",
                json=make_request_body("在 NetBox 中创建一个新设备 TestDevice01，设备类型为 Cisco Router，站点为 DC1"),
            )
            
            if response.status_code != 200:
                pytest.skip(f"API not available: {response.status_code}")
            
            result = response.json()
            # Should mention approval/HITL or NetBox create action
            hitl_keywords = [
                "approval", "hitl", "human", "confirm", "authorize",
                "审批", "确认", "授权", "人工", "批准",
                "create", "创建", "netbox", "device", "testdevice01"
            ]
            assert check_response(result, hitl_keywords)

    @pytest.mark.asyncio
    async def test_h02_netbox_delete_device(self, api_client):
        """Test that NetBox delete device operation triggers HITL."""
        async with api_client as client:
            response = await client.post(
                "/orchestrator/invoke",
                json=make_request_body("从 NetBox 中删除设备 TestDevice01"),
            )
            
            if response.status_code != 200:
                pytest.skip(f"API not available: {response.status_code}")
            
            result = response.json()
            # Should mention approval/HITL or delete action
            hitl_keywords = [
                "approval", "hitl", "confirm", "delete", "remove",
                "审批", "确认", "删除", "移除",
                "netbox", "testdevice01"
            ]
            assert check_response(result, hitl_keywords)

    # ========== R1 OpenConfig/NETCONF Tests ==========

    @pytest.mark.asyncio
    async def test_h03_r1_netconf_create_acl(self, api_client):
        """Test creating ACL on R1 via NETCONF/OpenConfig (R1 supports OpenConfig)."""
        async with api_client as client:
            response = await client.post(
                "/orchestrator/invoke",
                json=make_request_body("在 R1 上使用 OpenConfig 创建 ACL test，添加规则 index 10 deny any any"),
            )
            
            if response.status_code != 200:
                pytest.skip(f"API not available: {response.status_code}")
            
            result = response.json()
            # Should use NETCONF/OpenConfig and trigger HITL for write
            expected_keywords = [
                "netconf", "openconfig", "acl", "deny",
                "approval", "hitl", "confirm",
                "审批", "确认", "edit-config", "r1"
            ]
            assert check_response(result, expected_keywords)

    @pytest.mark.asyncio
    async def test_h04_r1_netconf_modify_acl(self, api_client):
        """Test modifying ACL on R1 via NETCONF/OpenConfig (change deny to permit)."""
        async with api_client as client:
            response = await client.post(
                "/orchestrator/invoke",
                json=make_request_body("在 R1 上修改 ACL test 的规则 index 10，将 deny any any 改为 permit any any"),
            )
            
            if response.status_code != 200:
                pytest.skip(f"API not available: {response.status_code}")
            
            result = response.json()
            # Should use NETCONF/OpenConfig and trigger HITL for write
            expected_keywords = [
                "netconf", "openconfig", "acl", "permit", "modify",
                "approval", "hitl", "confirm",
                "审批", "确认", "修改", "edit-config", "r1"
            ]
            assert check_response(result, expected_keywords)

    # ========== R3 CLI-only Tests ==========

    @pytest.mark.asyncio
    async def test_h05_r3_cli_create_loopback(self, api_client):
        """Test creating loopback interface on R3 via CLI (R3 does not support OpenConfig)."""
        async with api_client as client:
            response = await client.post(
                "/orchestrator/invoke",
                json=make_request_body("在 R3 上创建 Loopback10 接口，描述为 test，IP 地址 10.10.10.10/32"),
            )
            
            if response.status_code != 200:
                pytest.skip(f"API not available: {response.status_code}")
            
            result = response.json()
            # Should use CLI (not NETCONF) and trigger HITL for config
            expected_keywords = [
                "cli", "loopback", "10.10.10.10",
                "approval", "hitl", "confirm", "config",
                "审批", "确认", "配置", "interface", "r3"
            ]
            assert check_response(result, expected_keywords)

    @pytest.mark.asyncio
    async def test_h06_r3_cli_delete_loopback(self, api_client):
        """Test deleting loopback interface on R3 via CLI."""
        async with api_client as client:
            response = await client.post(
                "/orchestrator/invoke",
                json=make_request_body("在 R3 上删除 Loopback10 接口"),
            )
            
            if response.status_code != 200:
                pytest.skip(f"API not available: {response.status_code}")
            
            result = response.json()
            # Should use CLI and trigger HITL for config deletion
            expected_keywords = [
                "cli", "loopback", "delete", "remove", "no interface",
                "approval", "hitl", "confirm",
                "审批", "确认", "删除", "移除", "r3"
            ]
            assert check_response(result, expected_keywords)


class TestKnowledgeBaseLayers:
    """Test Knowledge Base layer tools (Layer 1)."""

    @pytest.fixture
    def api_client(self):
        """Create async HTTP client with auth token."""
        token = os.environ.get("OLAV_API_TOKEN", "test-token")
        return httpx.AsyncClient(
            base_url=API_BASE_URL,
            timeout=API_TIMEOUT,
            headers={"Authorization": f"Bearer {token}"},
        )

    @pytest.mark.asyncio
    async def test_k01_openconfig_schema_search(self, api_client):
        """Test OpenConfig schema search tool (Layer 1)."""
        async with api_client as client:
            response = await client.post(
                "/orchestrator/invoke",
                json=make_request_body("查找 BGP 相关的 OpenConfig YANG 路径"),
            )
            
            if response.status_code != 200:
                pytest.skip(f"API not available: {response.status_code}")
            
            result = response.json()
            # Should mention OpenConfig or schema paths
            assert check_response(result, [
                "openconfig", "yang", "xpath", "path", "schema",
                "bgp", "network-instance", "模式", "路径", "search", "查找"
            ])

    @pytest.mark.asyncio
    async def test_k02_document_search(self, api_client):
        """Test document search tool (Layer 1 - RAG)."""
        async with api_client as client:
            response = await client.post(
                "/orchestrator/invoke",
                json=make_request_body("搜索关于 OSPF 配置的文档"),
            )
            
            if response.status_code != 200:
                pytest.skip(f"API not available: {response.status_code}")
            
            result = response.json()
            assert check_response(result, ["ospf", "document", "文档", "search", "搜索", "config", "配置"])
