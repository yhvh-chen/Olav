import asyncio
import pytest
from types import SimpleNamespace

from olav.tools.nornir_tool import cli_tool
from olav.execution.backends.protocol import ExecutionResult
import olav.tools.nornir_tool as nornir_mod

class MockSandbox:
    def __init__(self):
        self.calls = []
        self.approval_mode = "approve"  # or "reject"

    async def execute_cli_command(self, device: str, command: str, use_textfsm: bool = True):
        self.calls.append(("query", device, command))
        if device == "nonexistent":
            return ExecutionResult(success=False, output="", error="Device 'nonexistent' not found", metadata={"reason": "not_found"})
        if "traceroute" in command:
            return ExecutionResult(success=False, output="", error="Command contains blacklisted pattern: 'traceroute'", metadata={"reason": "blacklist"})
        if "trace route" in command or "trace-route" in command:
            return ExecutionResult(success=False, output="", error="Command contains blacklisted pattern: 'trace route'", metadata={"reason": "blacklist"})
        if "reload" in command:
            return ExecutionResult(success=False, output="", error="Command contains blacklisted pattern: 'reload'", metadata={"reason": "blacklist"})
        # Simulate parsed output for interface brief
        if command == "show ip interface brief":
            parsed = [
                {"interface": "GigabitEthernet0/0", "ip_address": "192.168.1.1", "status": "up"},
                {"interface": "GigabitEthernet0/1", "ip_address": "unassigned", "status": "down"},
            ]
            return ExecutionResult(success=True, output=parsed, metadata={"parsed": True})
        return ExecutionResult(success=True, output="RAW_TEXT", metadata={"parsed": False})

    async def execute_cli_config(self, device: str, commands: list[str], requires_approval: bool = True):
        self.calls.append(("config", device, commands))
        if device == "nonexistent":
            return ExecutionResult(success=False, output="", error="Device 'nonexistent' not found", metadata={"reason": "not_found"})
        if self.approval_mode == "reject":
            return ExecutionResult(success=False, output="", error="Configuration rejected by user", metadata={"reason": "hitl_reject"})
        return ExecutionResult(success=True, output="CONFIG_APPLIED", metadata={"diff_captured": False})

@pytest.fixture(autouse=True)
def patch_sandbox(monkeypatch):
    # Patch global instance's sandbox with mock
    from olav.tools.nornir_tool import _nornir_tool_instance
    _nornir_tool_instance._sandbox = MockSandbox()
    yield _nornir_tool_instance._sandbox

@pytest.mark.asyncio
async def test_query_parsed_success(patch_sandbox):
    result = await cli_tool.ainvoke({"device": "R1", "command": "show ip interface brief"})
    assert result["success"] is True
    assert result["parsed"] is True
    assert isinstance(result["output"], list)
    assert len(result["output"]) == 2

@pytest.mark.asyncio
async def test_query_raw_fallback(patch_sandbox):
    result = await cli_tool.ainvoke({"device": "R1", "command": "show version"})
    assert result["success"] is True
    assert result["parsed"] is False
    assert isinstance(result["output"], str)

@pytest.mark.asyncio
async def test_query_blacklist_block(patch_sandbox):
    result = await cli_tool.ainvoke({"device": "R1", "command": "traceroute 8.8.8.8"})
    assert result["success"] is False
    assert "blacklisted" in result["error"].lower()

@pytest.mark.asyncio
async def test_query_blacklist_variants(patch_sandbox):
    result1 = await cli_tool.ainvoke({"device": "R1", "command": "trace route 8.8.8.8"})
    result2 = await cli_tool.ainvoke({"device": "R1", "command": "trace-route 8.8.8.8"})
    assert result1["success"] is False and "blacklisted" in result1["error"].lower()
    assert result2["success"] is False and "blacklisted" in result2["error"].lower()

@pytest.mark.asyncio
async def test_query_custom_blacklist_reload(patch_sandbox):
    result = await cli_tool.ainvoke({"device": "R1", "command": "reload in 5"})
    assert result["success"] is False
    assert "blacklisted" in result["error"].lower()

@pytest.mark.asyncio
async def test_query_device_not_found(patch_sandbox):
    result = await cli_tool.ainvoke({"device": "nonexistent", "command": "show ip interface brief"})
    assert result["success"] is False
    assert "not found" in result["error"].lower()

@pytest.mark.asyncio
async def test_config_command_success(patch_sandbox):
    result = await cli_tool.ainvoke({"device": "R1", "config_commands": ["interface Gi0/0", "mtu 9000"]})
    assert result["success"] is True
    assert "CONFIG_APPLIED" in result["output"]

@pytest.mark.asyncio
async def test_config_device_not_found(patch_sandbox):
    result = await cli_tool.ainvoke({"device": "nonexistent", "config_commands": ["interface Gi0/0", "mtu 9000"]})
    assert result["success"] is False
    assert "not found" in result["error"].lower()

@pytest.mark.asyncio
async def test_config_hitl_reject(monkeypatch, patch_sandbox):
    patch_sandbox.approval_mode = "reject"
    result = await cli_tool.ainvoke({"device": "R1", "config_commands": ["interface Gi0/0", "mtu 9000"]})
    assert result["success"] is False
    assert "rejected" in result["error"].lower()

@pytest.mark.asyncio
async def test_invalid_params_both_provided(patch_sandbox):
    result = await cli_tool.ainvoke({"device": "R1", "command": "show ip interface brief", "config_commands": ["interface Gi0/0"]})
    assert "error" in result
    assert "cannot provide" in result.get("error", "").lower()

@pytest.mark.asyncio
async def test_invalid_params_none_provided(patch_sandbox):
    result = await cli_tool.ainvoke({"device": "R1"})  # neither command nor config_commands
    assert "error" in result
    assert "must provide" in result.get("error", "").lower()
