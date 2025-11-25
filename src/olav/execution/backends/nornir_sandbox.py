"""Nornir sandbox backend with HITL approval and audit logging.

Enhancements added:
 - Command blacklist loading (env COLLECTOR_BLACKLIST_FILE)
 - Privilege level detection ("show privilege")
 - Optional auto enable escalation (env COLLECTOR_FORCE_ENABLE=1)
 - Structured error metadata (reason, resolution hints)
 - Parsed flag propagation for CLI queries
"""

import logging
import os
import re
from pathlib import Path

from config.settings import ToolConfig
from nornir import InitNornir
from nornir.core import Nornir

from olav.core.memory import OpenSearchMemory
from olav.core.settings import settings as env_settings
from olav.execution.backends.protocol import ExecutionResult, SandboxBackendProtocol

logger = logging.getLogger(__name__)


class ApprovalDecision:
    """Human approval decision for command execution."""

    def __init__(
        self,
        decision: str,
        modified_command: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Initialize approval decision.

        Args:
            decision: approve/edit/reject
            modified_command: Modified command if edited
            reason: Reason for decision
        """
        self.decision = decision
        self.modified_command = modified_command
        self.reason = reason


class NornirSandbox(SandboxBackendProtocol):
    """Nornir-based sandbox for NETCONF/gNMI operations with HITL."""

    def __init__(
        self,
        memory: OpenSearchMemory | None = None,
    ) -> None:
        """Initialize Nornir sandbox.

        Args:
            memory: OpenSearch memory instance for audit logging
        """
        self.nr: Nornir = InitNornir(
            runner={
                "plugin": "threaded",
                "options": {
                    "num_workers": ToolConfig.NORNIR_NUM_WORKERS,
                },
            },
            inventory={
                "plugin": "NBInventory",
                "options": {
                    "nb_url": env_settings.netbox_url,
                    "nb_token": env_settings.netbox_token,
                    "ssl_verify": False,
                    "filter_parameters": {"tag": ["olav-managed"]},
                },
            },
            logging={
                "enabled": False  # Use Python logging instead
            },
        )

        # Set device credentials from environment (NBInventory doesn't auto-populate)
        for host in self.nr.inventory.hosts.values():
            host.username = env_settings.device_username
            host.password = env_settings.device_password

            # Normalize NAPALM platform names (NetBox uses different conventions)
            if host.platform and host.platform.startswith("cisco_"):
                # cisco_ios → ios, cisco_nxos → nxos, cisco_iosxr → iosxr
                normalized = host.platform.replace("cisco_", "")
                logger.debug(
                    f"Normalizing platform for {host.name}: {host.platform} → {normalized}"
                )
                host.platform = normalized

        logger.info(f"Nornir initialized with {len(self.nr.inventory.hosts)} devices from NetBox")

        self.memory = memory or OpenSearchMemory()
        # Blacklist & privilege settings
        self.blacklist = self._load_blacklist()
        self.force_enable = os.getenv("COLLECTOR_FORCE_ENABLE", "0") == "1"
        self.min_privilege = int(os.getenv("COLLECTOR_MIN_PRIVILEGE", "15"))

    # --------------------------
    # Helper/utility methods
    # --------------------------
    def _load_blacklist(self) -> set[str]:
        """Load command blacklist from file and defaults.

        Default blocked commands include traceroute and destructive actions.
        Can extend via COLLECTOR_BLACKLIST_FILE (line-separated, case-insensitive).
        """
        default_block = {
            "traceroute",
            "trace route",
            "trace-route",
            "reload",
            "reboot",
            "write erase",
            "erase startup-config",
            "format",
            "delete flash:",
            "delete disk:",
        }
        blacklist: set[str] = set(default_block)
        fname = os.getenv("COLLECTOR_BLACKLIST_FILE", "command_blacklist.txt")
        candidates = [
            Path(fname),
            Path.cwd() / fname,
            Path("config") / fname,
        ]
        for path in candidates:
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip().lower()
                            if line and not line.startswith("#"):
                                blacklist.add(line)
                    logger.info(f"Loaded custom blacklist entries from {path}")
                    break
                except Exception as e:
                    logger.warning(f"Failed loading blacklist from {path}: {e}")
        return blacklist

    def _is_blacklisted(self, command: str) -> str | None:
        """Return matched blacklist pattern if command is blocked else None."""
        cmd = command.lower().strip()
        normalized = cmd.replace("-", " ")
        # Match whole-line or substring containment for dangerous patterns
        for blocked in self.blacklist:
            if blocked in normalized:
                return blocked
        return None

    def _get_privilege_level(self, device: str) -> int | None:
        """Attempt to detect current privilege level using 'show privilege'."""
        try:
            from nornir_netmiko.tasks import netmiko_send_command

            target = self.nr.filter(name=device)
            if not target.inventory.hosts:
                return None
            result = target.run(
                task=netmiko_send_command,
                command_string="show privilege",
                enable=False,
            )
            device_result = result[device]
            if device_result.failed:
                return None
            output = device_result.result or ""
            m = re.search(r"(Current )?privilege level (is )?(\d+)", output, flags=re.IGNORECASE)
            if m:
                return int(m.group(3))
            m2 = re.search(r"^\s*(\d+)\s*$", output, flags=re.MULTILINE)
            if m2:
                return int(m2.group(1))
            return None
        except Exception:
            return None

    def _should_escalate(self, privilege: int | None) -> bool:
        if privilege is None:
            return self.force_enable  # escalate if forced and unknown
        return privilege < self.min_privilege and self.force_enable

    def _is_write_operation(self, command: str) -> bool:
        """Determine if command is a write operation.

        Args:
            command: Command to analyze

        Returns:
            True if write operation
        """
        write_keywords = ["edit-config", "commit", "set", "delete", "replace"]
        return any(keyword in command.lower() for keyword in write_keywords)

    async def _request_approval(self, command: str) -> ApprovalDecision:
        """Request human approval for write operation.

        This triggers a LangGraph interrupt. The actual approval flow
        is handled by DeepAgents HumanInTheLoopMiddleware.

        Args:
            command: Command requiring approval

        Returns:
            Approval decision from human

        Note:
            This is a placeholder - actual implementation will use
            LangGraph's interrupt mechanism via SubAgent.interrupt_on
        """
        logger.warning(f"HITL approval required for: {command}")
        # In production, this will be an interrupt point
        # For now, return auto-approve for testing
        return ApprovalDecision(decision="approve")

    async def execute(
        self,
        command: str,
        device: str | None = None,
        background: bool = False,
        requires_approval: bool = True,
    ) -> ExecutionResult:
        """Execute NETCONF/gNMI command with optional HITL approval.

        Args:
            command: NETCONF/gNMI command to execute
            device: Target device hostname (optional, runs on all devices if None)
            background: Run in background (not supported yet)
            requires_approval: Whether to require HITL approval

        Returns:
            Execution result with success status and output
        """
        from config.settings import AgentConfig

        is_write = self._is_write_operation(command)

        # Request approval for write operations
        if is_write and requires_approval and AgentConfig.ENABLE_HITL:
            approval = await self._request_approval(command)

            if approval.decision == "reject":
                await self.memory.log_execution(
                    action="rejected",
                    command=command,
                    result={"reason": approval.reason},
                    user="system",
                )
                return ExecutionResult(
                    success=False,
                    output="",
                    error="Operation rejected by user",
                    metadata={"reason": approval.reason},
                )

            if approval.decision == "edit" and approval.modified_command:
                command = approval.modified_command
                logger.info(f"Command edited by user: {command}")

        # Execute command via Nornir
        try:
            # Filter to specific device if provided
            if device:
                # Nornir filter uses hostname field, not name
                target = self.nr.filter(filter_func=lambda h: h.name == device)
                if not target.inventory.hosts:
                    msg = f"Device '{device}' not found in inventory"
                    raise ValueError(msg)
            else:
                target = self.nr

            # 🔑 NETCONF Implementation via nornir-scrapli or nornir-napalm
            # For now, simulate NETCONF attempt to test fallback mechanism
            try:
                from nornir_napalm.plugins.tasks import napalm_get

                # Attempt NETCONF operation
                result = target.run(
                    task=napalm_get,
                    getters=["config"],
                )

                # Extract result
                if device:
                    device_result = result[device]
                    if device_result.failed:
                        raise Exception(device_result.exception or "NETCONF operation failed")
                    output = device_result.result
                else:
                    output = {name: r.result for name, r in result.items() if not r.failed}

                await self.memory.log_execution(
                    action="netconf_execute" if is_write else "netconf_query",
                    command=command,
                    result=output,
                    user="system",
                )

                return ExecutionResult(
                    success=True,
                    output=str(output),
                    metadata={"is_write": is_write, "device": device},
                )

            except ImportError:
                # nornir-napalm not installed - return specific error
                msg = (
                    "NETCONF not available: nornir-napalm plugin not installed. "
                    "Install with: uv add nornir-napalm"
                )
                raise ConnectionRefusedError(msg)

        except ConnectionRefusedError as e:
            # 🔑 Return specific error to trigger CLI fallback
            logger.warning(f"NETCONF connection failed for device {device}: {e}")
            await self.memory.log_execution(
                action="netconf_connection_refused",
                command=command,
                result={"error": str(e), "device": device},
                user="system",
            )
            return ExecutionResult(
                success=False,
                output="",
                error=f"NETCONF connection refused: {e!s}. Device may not support NETCONF on port 830.",
                metadata={"device": device, "should_fallback_to_cli": True},
            )
        except Exception as e:
            logger.error(f"NETCONF command execution failed: {e}")
            await self.memory.log_execution(
                action="netconf_error",
                command=command,
                result={"error": str(e), "device": device},
                user="system",
            )
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                metadata={"device": device},
            )

    async def read(self, path: str) -> str:
        """Read configuration from device.

        Args:
            path: XPath to read

        Returns:
            Configuration as string
        """
        result = await self.execute(f"get-config {path}", requires_approval=False)
        return result.output

    async def write(self, path: str, content: str) -> None:
        """Write configuration to device.

        Args:
            path: XPath to write to
            content: Configuration content
        """
        command = f"edit-config {path} {content}"
        await self.execute(command, requires_approval=True)

    async def execute_cli_command(
        self,
        device: str,
        command: str,
        use_textfsm: bool = True,
    ) -> ExecutionResult:
        """Execute read-only CLI command via Netmiko.

        Args:
            device: Target device hostname
            command: CLI command to execute
            use_textfsm: Whether to parse output with TextFSM

        Returns:
            Execution result with parsed output if TextFSM enabled
        """
        # Pre-flight: blacklist
        blocked = self._is_blacklisted(command)
        if blocked:
            reason = f"Command contains blacklisted pattern: '{blocked}'"
            resolution = "使用安全的查询替代；禁止执行潜在危险/破坏性命令。"
            await self.memory.log_execution(
                action="cli_blacklist_block",
                command=command,
                result={"error": reason, "device": device},
                user="system",
            )
            return ExecutionResult(
                success=False,
                output="",
                error=reason,
                metadata={"device": device, "reason": reason, "resolution": resolution},
            )

        # Privilege detection & optional escalation
        privilege = self._get_privilege_level(device)
        escalate = self._should_escalate(privilege)

        try:
            from nornir_netmiko.tasks import netmiko_send_command

            target = self.nr.filter(name=device)
            if not target.inventory.hosts:
                msg = f"Device '{device}' not found in inventory"
                raise ValueError(msg)

            result = target.run(
                task=netmiko_send_command,
                command_string=command,
                use_textfsm=use_textfsm,
                enable=escalate,
            )

            device_result = result[device]
            if device_result.failed:
                raise Exception(device_result.exception or "Command failed")

            output = device_result.result

            parsed_flag = use_textfsm and isinstance(output, (list, dict))

            await self.memory.log_execution(
                action="cli_query",
                command=command,
                result={
                    "output": output,
                    "parsed": parsed_flag,
                    "privilege": privilege,
                    "escalated": escalate,
                },
                user="system",
            )

            return ExecutionResult(
                success=True,
                output=output,
                metadata={
                    "parsed": parsed_flag,
                    "device": device,
                    "privilege": privilege,
                    "escalated": escalate,
                },
            )

        except Exception as e:
            reason = str(e)
            resolution = "检查设备连接、命令语法或特权级；必要时提升为 enable 模式。"
            logger.error(f"CLI command execution failed: {reason}")
            await self.memory.log_execution(
                action="cli_error",
                command=command,
                result={"error": reason, "device": device},
                user="system",
            )
            return ExecutionResult(
                success=False,
                output="",
                error=reason,
                metadata={"device": device, "reason": reason, "resolution": resolution},
            )

    async def execute_cli_config(
        self,
        device: str,
        commands: list[str],
        requires_approval: bool = True,
    ) -> ExecutionResult:
        """Execute configuration commands via Netmiko (with HITL approval).

        Args:
            device: Target device hostname
            commands: List of configuration commands
            requires_approval: Whether to require HITL approval

        Returns:
            Execution result

        Note:
            ⚠️ CLI mode has no atomic rollback - backup running-config first
        """
        from config.settings import AgentConfig

        # Request approval for config commands
        command_str = "; ".join(commands)
        if requires_approval and AgentConfig.ENABLE_HITL:
            approval = await self._request_approval(command_str)

            if approval.decision == "reject":
                await self.memory.log_execution(
                    action="cli_config_rejected",
                    command=command_str,
                    result={"reason": approval.reason},
                    user="system",
                )
                return ExecutionResult(
                    success=False,
                    output="",
                    error="Configuration rejected by user",
                    metadata={"reason": approval.reason},
                )

            if approval.decision == "edit" and approval.modified_command:
                commands = approval.modified_command.split(";")
                logger.info(f"Commands edited by user: {commands}")

        try:
            import difflib

            from nornir_netmiko.tasks import netmiko_send_command, netmiko_send_config

            # Filter to specific device
            target = self.nr.filter(name=device)
            if not target.inventory.hosts:
                msg = f"Device '{device}' not found in inventory"
                raise ValueError(msg)

            capture_diff = os.getenv("COLLECTOR_CAPTURE_DIFF", "1") == "1"

            before_cfg = ""
            if capture_diff:
                try:
                    before_res = target.run(
                        task=netmiko_send_command,
                        command_string="show running-config",
                        enable=True,
                    )
                    device_before = before_res[device]
                    if not device_before.failed:
                        before_cfg = device_before.result or ""
                except Exception as e:
                    logger.debug(f"Failed capturing pre-change config: {e}")

            # Execute configuration commands
            result = target.run(
                task=netmiko_send_config,
                config_commands=commands,
            )

            device_result = result[device]
            if device_result.failed:
                raise Exception(device_result.exception or "Configuration failed")

            output = device_result.result

            after_cfg = ""
            diff_text = None
            if capture_diff:
                try:
                    after_res = target.run(
                        task=netmiko_send_command,
                        command_string="show running-config",
                        enable=True,
                    )
                    device_after = after_res[device]
                    if not device_after.failed:
                        after_cfg = device_after.result or ""
                        if before_cfg and after_cfg:
                            diff_lines = difflib.unified_diff(
                                before_cfg.splitlines(),
                                after_cfg.splitlines(),
                                fromfile="before",
                                tofile="after",
                                lineterm="",
                            )
                            diff_text = "\n".join(diff_lines)
                except Exception as e:
                    logger.debug(f"Failed capturing post-change config/diff: {e}")

            audit_payload = {
                "output": output,
                "commands": commands,
                "captured_diff": bool(diff_text),
                "diff": diff_text[:20000] if diff_text else None,
            }

            await self.memory.log_execution(
                action="cli_config",
                command=command_str,
                result=audit_payload,
                user="system",
            )

            return ExecutionResult(
                success=True,
                output=output,
                metadata={
                    "device": device,
                    "commands": commands,
                    "diff_captured": bool(diff_text),
                },
            )

        except Exception as e:
            reason = str(e)
            resolution = "检查命令语法、设备特权或连接状态；必要时分步下发。"
            logger.error(f"CLI configuration failed: {reason}")
            await self.memory.log_execution(
                action="cli_config_error",
                command=command_str,
                result={"error": reason, "device": device},
                user="system",
            )
            return ExecutionResult(
                success=False,
                output="",
                error=reason,
                metadata={"device": device, "reason": reason, "resolution": resolution},
            )
