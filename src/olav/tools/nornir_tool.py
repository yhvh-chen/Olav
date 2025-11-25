"""Nornir NETCONF/CLI tool wrapper with timing metadata.

Adds `__meta__.elapsed_sec` to each tool response for performance profiling.
"""

import logging
import time
from pathlib import Path
from typing import Any

# Derive CONFIG_DIR without importing non-packaged root module
CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"

from langchain_core.tools import tool

from olav.execution.backends.nornir_sandbox import NornirSandbox

logger = logging.getLogger(__name__)


class NornirTool:
    """LangChain tool wrapper for Nornir sandbox operations."""

    def __init__(self, sandbox: NornirSandbox | None = None) -> None:
        """Initialize Nornir tool.

        Args:
            sandbox: Nornir sandbox instance (lazy initialization if None)
        """
        self._sandbox = sandbox

    @property
    def sandbox(self) -> NornirSandbox:
        """Lazy-load Nornir sandbox (avoids NetBox connection at import time)."""
        if self._sandbox is None:
            self._sandbox = NornirSandbox()
        return self._sandbox


# Create global instance
_nornir_tool_instance = NornirTool()


@tool
async def netconf_tool(
    device: str,
    operation: str,
    xpath: str | None = None,
    payload: str | None = None,
) -> dict[str, Any]:
    """Execute NETCONF operation on network device.

    **CRITICAL**: This tool triggers HITL approval for write operations.
    Read operations (get-config) execute immediately.

    Args:
        device: Target device hostname
        operation: NETCONF operation (get-config, edit-config)
        xpath: XPath filter (required for get-config)
        payload: XML payload (required for edit-config)

    Returns:
        Execution result with status and output

    错误处理:
        如果连接失败，返回明确错误信息以便 Root Agent 降级到 CLI

    Example:
        >>> await netconf_tool(
        ...     device="router1",
        ...     operation="get-config",
        ...     xpath="/interfaces/interface/state"
        ... )
    """
    start = time.perf_counter()
    # 参数验证
    if operation == "get-config" and not xpath:
        return {
            "error": "get-config requires xpath parameter",
            "__meta__": {"elapsed_sec": round(time.perf_counter() - start, 6)},
        }
    if operation == "edit-config" and not payload:
        return {
            "error": "edit-config requires payload parameter",
            "__meta__": {"elapsed_sec": round(time.perf_counter() - start, 6)},
        }

    # 构造 RPC 与审批标记
    if operation == "get-config":
        command = f"<get-config><source><running/></source><filter type='xpath' select='{xpath}'/></get-config>"
        requires_approval = False
    elif operation == "edit-config":
        command = (
            f"<edit-config><target><candidate/></target><config>{payload}</config></edit-config>"
        )
        requires_approval = True
    else:
        return {
            "error": f"Unsupported operation: {operation}",
            "__meta__": {"elapsed_sec": round(time.perf_counter() - start, 6)},
        }

    try:
        result = await _nornir_tool_instance.sandbox.execute(
            command=command,
            device=device,
            requires_approval=requires_approval,
        )
        return {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "__meta__": {"elapsed_sec": round(time.perf_counter() - start, 6)},
        }
    except ConnectionRefusedError as e:
        return {
            "success": False,
            "error": f"NETCONF connection failed: Connection refused on port 830. 设备可能不支持 NETCONF。原始错误: {e}",
            "__meta__": {"elapsed_sec": round(time.perf_counter() - start, 6)},
        }
    except TimeoutError as e:
        return {
            "success": False,
            "error": f"NETCONF connection failed: Timeout connecting to port 830. 原始错误: {e}",
            "__meta__": {"elapsed_sec": round(time.perf_counter() - start, 6)},
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"NETCONF connection failed: {e}",
            "__meta__": {"elapsed_sec": round(time.perf_counter() - start, 6)},
        }


@tool
async def cli_tool(
    device: str,
    command: str | None = None,
    config_commands: list[str] | None = None,
) -> dict[str, Any]:
    """Execute CLI commands on network device via SSH.

    **CRITICAL**: Configuration commands trigger HITL approval.
    Read commands execute immediately with TextFSM parsing.

    Args:
        device: Target device hostname
        command: Single read command (for queries)
        config_commands: List of configuration commands (for changes)

    Returns:
        Execution result with parsed output (TextFSM for read, raw for config)

    Example (Read):
        >>> await cli_tool(
        ...     device="router1",
        ...     command="show ip interface brief"
        ... )
        {
            "success": True,
            "output": [
                {"interface": "GigabitEthernet0/0", "ip_address": "192.168.1.1", "status": "up"},
                ...
            ],
            "parsed": True
        }

    Example (Write):
        >>> await cli_tool(
        ...     device="router1",
        ...     config_commands=["interface GigabitEthernet0/0", "mtu 9000"]
        ... )
        # Triggers HITL approval
    """
    start = time.perf_counter()
    # 验证参数
    if not command and not config_commands:
        return {
            "error": "Must provide either command or config_commands",
            "__meta__": {"elapsed_sec": round(time.perf_counter() - start, 6)},
        }
    if command and config_commands:
        return {
            "error": "Cannot provide both command and config_commands",
            "__meta__": {"elapsed_sec": round(time.perf_counter() - start, 6)},
        }

    # 判断是否为配置操作
    is_config = config_commands is not None
    requires_approval = is_config

    try:
        if is_config:
            # 配置命令（需要审批）
            result = await _nornir_tool_instance.sandbox.execute_cli_config(
                device=device,
                commands=config_commands,
                requires_approval=requires_approval,
            )
        else:
            # 查询命令（自动 TextFSM 解析）
            result = await _nornir_tool_instance.sandbox.execute_cli_command(
                device=device,
                command=command,
                use_textfsm=True,
            )

        return {
            "success": result.success,
            "output": result.output,
            "parsed": result.metadata.get("parsed", False) if result.metadata else False,
            "error": result.error,
            "__meta__": {"elapsed_sec": round(time.perf_counter() - start, 6)},
        }
    except ConnectionRefusedError as e:
        return {
            "success": False,
            "error": f"SSH connection failed: Connection refused on port 22. 原始错误: {e!s}",
            "__meta__": {"elapsed_sec": round(time.perf_counter() - start, 6)},
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"CLI execution failed: {e!s}",
            "__meta__": {"elapsed_sec": round(time.perf_counter() - start, 6)},
        }
