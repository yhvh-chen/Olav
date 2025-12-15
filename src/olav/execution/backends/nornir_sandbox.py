"""Nornir sandbox backend with HITL approval and audit logging.

Enhancements added:
 - Command blacklist loading (env COLLECTOR_BLACKLIST_FILE)
 - Privilege level detection ("show privilege")
 - Optional auto enable escalation (env COLLECTOR_FORCE_ENABLE=1)
 - Structured error metadata (reason, resolution hints)
 - Parsed flag propagation for CLI queries
"""

import logging
import re
import json
from pathlib import Path

from config.settings import settings
from nornir import InitNornir
from nornir.core import Nornir
from nornir.core.inventory import ConnectionOptions

from olav.core.memory import OpenSearchMemory
from config.settings import settings
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
                    "num_workers": settings.nornir_num_workers,
                },
            },
            inventory={
                "plugin": "NBInventory",
                "options": {
                    "nb_url": settings.netbox_url,
                    "nb_token": settings.netbox_token,
                    "ssl_verify": False,
                    "filter_parameters": {"tag": ["suzieq"]},
                },
            },
            logging={
                "enabled": False  # Use Python logging instead
            },
        )

        # Set device credentials from environment (NBInventory doesn't auto-populate)
        for host in self.nr.inventory.hosts.values():
            host.username = settings.device_username
            host.password = settings.device_password

            # Ensure Netmiko has an enable secret available when enable=True is used
            # (e.g., for show running-config in config diff capture).
            existing_netmiko = host.connection_options.get("netmiko")
            if existing_netmiko is None:
                host.connection_options["netmiko"] = ConnectionOptions(
                    extras={"secret": settings.device_enable_password}
                )
            else:
                merged_extras = dict(existing_netmiko.extras or {})
                merged_extras.setdefault("secret", settings.device_enable_password)
                host.connection_options["netmiko"] = ConnectionOptions(
                    hostname=existing_netmiko.hostname,
                    port=existing_netmiko.port,
                    username=existing_netmiko.username,
                    password=existing_netmiko.password,
                    platform=existing_netmiko.platform,
                    extras=merged_extras,
                )

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
        # Blacklist & privilege settings (from centralized settings)
        self.blacklist = self._load_blacklist()
        self.force_enable = settings.collector_force_enable
        self.min_privilege = settings.collector_min_privilege

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
        fname = settings.collector_blacklist_file
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
        _background: bool = False,
        requires_approval: bool = True,
    ) -> ExecutionResult:
        """Execute NETCONF/gNMI command with optional HITL approval.

        Args:
            command: NETCONF/gNMI command to execute
            device: Target device hostname (optional, runs on all devices if None)
            _background: Run in background (not implemented, for interface compatibility)
            requires_approval: Whether to require HITL approval

        Returns:
            Execution result with success status and output
        """
        from config.settings import settings

        is_write = self._is_write_operation(command)

        # Request approval for write operations
        if is_write and requires_approval and settings.enable_hitl:
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

            # 🔑 NETCONF Implementation (ncclient)
            # NOTE: do not confuse NAPALM (SSH/CLI) with NETCONF.
            try:
                from ncclient import manager

                # Filter to specific device if provided
                if not device:
                    raise ValueError("NETCONF execution requires a specific device")

                host = target.inventory.hosts.get(device)
                if host is None:
                    raise ValueError(f"Device '{device}' not found in inventory")

                hostname = host.hostname or host.name
                port = int(host.data.get("netconf_port", 830)) if isinstance(host.data, dict) else 830

                def _extract_xpath(cmd: str) -> str | None:
                    import re

                    m = re.search(r"select=([\"'])(?P<xp>.*?)(\1)", cmd)
                    return m.group("xp") if m else None

                def _extract_config_payload(cmd: str) -> str | None:
                    import re

                    m = re.search(r"<config>(?P<payload>.*)</config>", cmd, flags=re.DOTALL)
                    if not m:
                        return None
                    # ncclient expects the provided config to be rooted in the NETCONF <config> element
                    # (in the NETCONF base namespace), not directly in the OpenConfig/native payload.
                    inner = m.group("payload")
                    return (
                        '<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">'
                        f"{inner}"
                        "</config>"
                    )

                # Determine op from the command wrapper we generate in NetconfTool
                is_get = "<get-config" in command
                is_edit = "<edit-config" in command
                if not (is_get or is_edit):
                    raise ValueError("Unsupported NETCONF RPC wrapper; expected <get-config> or <edit-config>")

                with manager.connect(
                    host=hostname,
                    port=port,
                    username=host.username,
                    password=host.password,
                    hostkey_verify=False,
                    allow_agent=False,
                    look_for_keys=False,
                    # Avoid ncclient raising opaque XMLError; return rpc-reply so we can inspect <rpc-error>
                    errors_params={"raise_mode": 0},
                    timeout=30,
                ) as m:
                    if is_get:
                        xpath = _extract_xpath(command)
                        if not xpath:
                            raise ValueError("Missing xpath filter in get-config")

                        reply = m.get_config(source="running", filter=("xpath", xpath))
                        output: Any = reply.xml
                        action = "netconf_query"
                    else:
                        payload = _extract_config_payload(command)
                        if not payload:
                            raise ValueError("Missing <config> payload in edit-config")

                        reply = m.edit_config(target="running", config=payload)
                        output = reply.xml
                        # With raise_mode=0, rpc-errors do not raise; detect them via reply.ok
                        if getattr(reply, "ok", True) is False:
                            return ExecutionResult(
                                success=False,
                                output=output,
                                error="NETCONF rpc-error (see output for <rpc-error> details)",
                                metadata={
                                    "is_write": is_write,
                                    "device": device,
                                    "host": hostname,
                                    "port": port,
                                },
                            )
                        action = "netconf_execute"

                await self.memory.log_execution(
                    action=action,
                    command=command,
                    result={"device": device, "host": hostname, "port": port},
                    user="system",
                )

                return ExecutionResult(
                    success=True,
                    output=output,
                    metadata={"is_write": is_write, "device": device, "host": hostname, "port": port},
                )

            except ImportError:
                msg = "NETCONF not available: ncclient not installed. Install with: uv add ncclient"
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
            # Try to surface server-side rpc-error details (bad-element, error-path, etc.)
            rpc_error_details: dict[str, object] | None = None
            try:
                from ncclient.operations.errors import OperationError  # type: ignore
                from ncclient.operations.rpc import RPCError  # type: ignore

                def _rpc_error_to_dict(err: object) -> dict[str, object]:
                    return {
                        "error_type": getattr(err, "type", None),
                        "error_tag": getattr(err, "tag", None),
                        "error_severity": getattr(err, "severity", None),
                        "error_message": getattr(err, "message", None),
                        "error_path": getattr(err, "path", None),
                        "bad_element": getattr(err, "bad_element", None),
                        "error_info": getattr(err, "info", None),
                        "error_xml": getattr(err, "xml", None),
                    }

                if isinstance(e, RPCError):
                    rpc_error_details = _rpc_error_to_dict(e)
                elif isinstance(e, OperationError):
                    errs = getattr(e, "errors", None)
                    if isinstance(errs, list) and errs:
                        rpc_error_details = {
                            "operation_error": True,
                            "rpc_errors": [_rpc_error_to_dict(one) for one in errs[:5]],
                        }
            except Exception:
                rpc_error_details = None

            # Fallback: include exception type/args and any obvious structured fields
            if not rpc_error_details:
                generic: dict[str, object] = {
                    "exc_type": type(e).__name__,
                    "exc_args": getattr(e, "args", None),
                    "exc_repr": repr(e),
                }
                maybe_errors = getattr(e, "errors", None)
                if isinstance(maybe_errors, list) and maybe_errors:
                    generic["errors"] = [repr(one) for one in maybe_errors[:5]]
                maybe_xml = getattr(e, "xml", None)
                if maybe_xml:
                    generic["error_xml"] = maybe_xml
                rpc_error_details = generic

            err_text = str(e)
            if rpc_error_details:
                err_text = f"{err_text} | rpc_error={json.dumps(rpc_error_details, ensure_ascii=False)}"

            logger.error(f"NETCONF command execution failed: {err_text}")
            await self.memory.log_execution(
                action="netconf_error",
                command=command,
                result={"error": err_text, "device": device},
                user="system",
            )
            return ExecutionResult(
                success=False,
                output="",
                error=err_text,
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
            resolution = "Use safe query alternatives; dangerous/destructive commands are prohibited."
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

            # Try with TextFSM first, fallback to raw text if parsing fails
            textfsm_failed = False
            if use_textfsm:
                result = target.run(
                    task=netmiko_send_command,
                    command_string=command,
                    use_textfsm=True,
                    enable=escalate,
                )
                device_result = result[device]

                # Check if TextFSM parsing failed (exception contains "TextFSM" or "State Error")
                if device_result.failed:
                    error_str = str(device_result.exception or "")
                    if "TextFSM" in error_str or "State Error" in error_str:
                        logger.warning(
                            f"TextFSM parsing failed for '{command}' on {device}, "
                            f"falling back to raw text: {error_str[:100]}"
                        )
                        textfsm_failed = True
                    else:
                        raise Exception(device_result.exception or "Command failed")

            # Retry without TextFSM if parsing failed, or if use_textfsm=False
            if textfsm_failed or not use_textfsm:
                result = target.run(
                    task=netmiko_send_command,
                    command_string=command,
                    use_textfsm=False,
                    enable=escalate,
                )
                device_result = result[device]
                if device_result.failed:
                    raise Exception(device_result.exception or "Command failed")

            output = device_result.result

            parsed_flag = use_textfsm and not textfsm_failed and isinstance(output, (list, dict))

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
            resolution = "Check device connection, command syntax, or privilege level; escalate to enable mode if needed."
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
        from config.settings import settings

        # Request approval for config commands
        command_str = "; ".join(commands)
        if requires_approval and settings.enable_hitl:
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

            capture_diff = settings.collector_capture_diff

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

            device_result = result.get(device)
            if device_result is None:
                keys = list(result.keys())
                raise Exception(
                    f"No Nornir result returned for device '{device}' (keys={keys}). "
                    "Likely connection/authentication failure."
                )
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
            resolution = "Check command syntax, device privilege, or connection status; consider sending commands in steps."
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
