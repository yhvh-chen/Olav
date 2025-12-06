"""Expert Mode Deep Analyzer - Phase 2 realtime verification.

The Deep Analyzer:
1. Receives suspected issues from Phase 1 (Quick Analyzer)
2. Uses OpenConfig/CLI tools for realtime device access
3. Verifies hypotheses with current device state
4. Returns high-confidence findings (95%)

This is the "Deep" phase in the Quick/Deep two-phase architecture.
Only uses OpenConfig and CLI tools - no SuzieQ (historical data).

Tools:
- openconfig_schema_search: Find OpenConfig XPaths for config analysis
- netconf_get: Read realtime config via NETCONF (OpenConfig/Native)
- cli_show: Execute CLI show commands (vendor-specific)
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from olav.core.llm import LLMFactory
from olav.modes.expert.supervisor import (
    LAYER_INFO,
    REALTIME_CONFIDENCE,
    DiagnosisResult,
    DiagnosisTask,
)
from olav.modes.shared.debug import DebugContext
from olav.tools.config_extractor import ConfigSectionExtractor

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class DeepAnalyzerResult:
    """Result from DeepAnalyzer workflow integration."""
    success: bool
    confidence: float
    findings: list[str]
    root_cause_found: bool = False
    root_cause: str | None = None
    tool_outputs: list[dict] = field(default_factory=list)


# =============================================================================
# Prompts
# =============================================================================

DEEP_ANALYZER_SYSTEM_PROMPT = """你是网络故障诊断专家 OLAV 的深度分析器，负责通过实时设备访问验证故障假设。

## 当前任务
- **层级**: {layer} ({layer_name})
- **假设**: {hypothesis}
- **可疑设备**: {suspected_devices}

## Phase 1 发现 (SuzieQ 历史数据)
{phase1_findings}

## 你的任务
1. 使用 OpenConfig/CLI 工具读取设备**实时配置**
2. 验证 Phase 1 假设是否正确
3. 如果发现根因，提供明确证据

## 可用工具
- **openconfig_schema_search**: 查找 OpenConfig XPath
- **netconf_get**: NETCONF 读取实时配置
- **cli_show**: CLI show 命令 (厂商特定)

## 关键检查点 (路由策略问题)
1. `show run | section route-map` - 查看 route-map 配置
2. `show run | section prefix-list` - 查看 prefix-list 配置
3. `show bgp neighbors X.X.X.X policy` - 查看 BGP 邻居策略
4. `show ip bgp X.X.X.X/X longer-prefixes` - 验证前缀是否被通告

## 输出格式
分析完成后，总结：
- **根因确认**: 是否确认根因
- **证据**: 具体配置行或状态
- **置信度**: 0.0-0.95 (实时数据上限)
- **建议修复**: 具体修改建议 (只读模式，不执行)
"""


# =============================================================================
# Deep Analyzer
# =============================================================================


class DeepAnalyzer:
    """Phase 2 analyzer for realtime device verification.

    Uses OpenConfig/CLI tools to verify hypotheses from Phase 1.
    Only accesses live devices - no historical SuzieQ data.

    Usage:
        analyzer = DeepAnalyzer()
        task = DiagnosisTask(
            task_id=2,
            layer="L4",
            description="Verify BGP route-map on R1/R2 blocking 10.0.0.0/16",
            suggested_filters={"hostname": ["R1", "R2"]},
        )
        result = await analyzer.execute(
            task=task,
            phase1_findings=["R3/R4 missing route to 10.0.0.0/16"],
            hypothesis="BGP route-map/prefix-list on R1/R2 blocking advertisement"
        )
    """

    def __init__(
        self,
        max_iterations: int = 5,
        debug_context: DebugContext | None = None,
    ) -> None:
        """Initialize Deep Analyzer.

        Args:
            max_iterations: Maximum ReAct iterations per task.
            debug_context: Optional debug context for instrumentation.
        """
        self.max_iterations = max_iterations
        self.debug_context = debug_context
        self.llm = LLMFactory.get_chat_model()
        self.config_extractor = ConfigSectionExtractor()

    def _get_realtime_tools(self) -> list[Any]:
        """Get OpenConfig and CLI tools for realtime device access.

        Returns:
            List of LangChain tools for realtime data.

        Note:
            Only includes tools that access live devices.
            NO SuzieQ tools - this is Phase 2 (realtime only).
        """
        from langchain_core.tools import tool

        tools = []

        # Capture config_extractor in closure
        config_extractor = self.config_extractor

        # CLI show tool - direct Nornir access
        @tool
        async def cli_show(device: str, command: str) -> str:
            """Execute CLI show command on a network device.

            Use this to read device configuration or state in realtime.

            Args:
                device: Target device hostname (e.g., "R1", "R2")
                command: CLI command (e.g., "show run | section route-map")

            Returns:
                Command output as string.

            Example commands for BGP policy investigation:
            - "show run | section route-map"
            - "show run | section ip prefix-list"
            - "show ip bgp neighbors X.X.X.X policy"
            - "show ip bgp X.X.X.X"
            """
            try:
                from olav.execution.backends.nornir_sandbox import NornirSandbox

                sandbox = NornirSandbox()
                result = await sandbox.execute_cli_command(
                    device=device,
                    command=command,
                    use_textfsm=False,  # Raw text for config sections
                )

                if result.success:
                    # Use config extractor to reduce token usage
                    output = result.output
                    if len(output) > 2000:
                        # Extract relevant sections for policy analysis
                        sections = config_extractor.extract(
                            output,
                            ["route-map", "prefix-list", "bgp", "acl"]
                        )
                        if sections:
                            extracted = "\n\n".join(
                                f"=== {name} ===\n{content}"
                                for name, content in sections.items()
                                if content.strip()
                            )
                            if extracted:
                                return f"[Extracted from {len(output)} chars]\n{extracted}"
                    return output
                return f"Error: {result.error}"

            except Exception as e:
                logger.error(f"CLI show failed for {device}: {e}")
                return f"Error executing CLI command on {device}: {e}"

        tools.append(cli_show)

        # OpenConfig schema search (optional)
        try:
            from olav.tools.opensearch_tool import OpenConfigSchemaTool

            schema_tool_instance = OpenConfigSchemaTool()

            @tool
            async def openconfig_schema_search(query: str) -> str:
                """Search OpenConfig YANG schema for configuration paths.

                Use this to find the correct XPath for NETCONF queries.

                Args:
                    query: Search query (e.g., "bgp neighbor", "route-map", "prefix-list")

                Returns:
                    Matching OpenConfig paths and descriptions.
                """
                try:
                    result = await schema_tool_instance.execute(query=query)
                    if hasattr(result, "data"):
                        import json
                        return json.dumps(result.data[:5], indent=2, ensure_ascii=False)
                    return str(result)
                except Exception as e:
                    return f"Schema search error: {e}"

            tools.append(openconfig_schema_search)
        except ImportError:
            logger.debug("OpenConfig schema tool not available")

        logger.info(f"DeepAnalyzer initialized with {len(tools)} realtime tools")
        return tools

    async def execute(
        self,
        task: DiagnosisTask,
        phase1_findings: list[str],
        hypothesis: str,
    ) -> DiagnosisResult:
        """Execute Phase 2 verification using realtime device access.

        Args:
            task: Task from Supervisor (includes suspected devices).
            phase1_findings: Findings from Phase 1 (Quick Analyzer).
            hypothesis: Hypothesis to verify.

        Returns:
            DiagnosisResult with high-confidence findings.
        """
        layer_info = LAYER_INFO.get(task.layer, {})
        suspected_devices = task.suggested_filters.get("hostname", [])

        # Format phase1 findings
        phase1_text = "\n".join(f"- {f}" for f in phase1_findings) if phase1_findings else "无"

        # Build prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", DEEP_ANALYZER_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="messages"),
        ])

        prompt.partial(
            layer=task.layer,
            layer_name=layer_info.get("name", "Unknown"),
            hypothesis=hypothesis,
            suspected_devices=", ".join(suspected_devices) if suspected_devices else "未指定",
            phase1_findings=phase1_text,
        )

        # Get realtime tools
        tools = self._get_realtime_tools()

        if not tools:
            return DiagnosisResult(
                task_id=task.task_id,
                layer=task.layer,
                success=False,
                confidence=0.0,
                findings=["Realtime tools not available"],
                error="No OpenConfig/CLI tools configured",
            )

        # Create ReAct agent
        try:
            from langgraph.errors import GraphRecursionError
            from langgraph.prebuilt import create_react_agent

            # Build input message
            input_msg = f"""验证假设: {hypothesis}

可疑设备: {', '.join(suspected_devices) if suspected_devices else '根据 Phase 1 发现确定'}

Phase 1 发现:
{phase1_text}

请使用 OpenConfig/CLI 工具验证假设，检查实时设备配置。

关键命令参考:
- `cli_show(device="R1", command="show run | section route-map")`
- `cli_show(device="R1", command="show run | section prefix-list")`
- `cli_show(device="R1", command="show ip bgp neighbors")`
"""

            logger.debug(f"DeepAnalyzer input: {input_msg}")
            logger.debug(f"DeepAnalyzer tools: {[t.name for t in tools]}")

            agent = create_react_agent(self.llm, tools)

            tool_outputs = []
            collected_messages = []

            input_messages = [
                SystemMessage(content=DEEP_ANALYZER_SYSTEM_PROMPT.format(
                    layer=task.layer,
                    layer_name=layer_info.get("name", "Unknown"),
                    hypothesis=hypothesis,
                    suspected_devices=", ".join(suspected_devices) if suspected_devices else "未指定",
                    phase1_findings=phase1_text,
                )),
                ("user", input_msg),
            ]

            try:
                async for chunk in agent.astream(
                    {"messages": input_messages},
                    config={"recursion_limit": 15},
                    stream_mode="updates",
                ):
                    for _node_name, node_data in chunk.items():
                        if "messages" in node_data:
                            for msg in node_data["messages"]:
                                collected_messages.append(msg)
                                msg_type = type(msg).__name__

                                if msg_type == "ToolMessage":
                                    tool_content = getattr(msg, "content", "")
                                    if isinstance(tool_content, str) and len(tool_content) > 50:
                                        tool_outputs.append({"raw": tool_content[:3000]})
                                    elif isinstance(tool_content, dict):
                                        tool_outputs.append(tool_content)

            except GraphRecursionError:
                logger.warning(f"DeepAnalyzer hit recursion limit - {len(tool_outputs)} tool outputs collected")

            # Extract final analysis from messages
            findings, confidence, _root_cause = self._extract_analysis(collected_messages, tool_outputs)

            return DiagnosisResult(
                task_id=task.task_id,
                layer=task.layer,
                success=True,
                confidence=min(confidence, REALTIME_CONFIDENCE),
                findings=findings,
                tool_outputs=tool_outputs,
                error=None,
            )

        except Exception as e:
            logger.exception(f"DeepAnalyzer failed: {e}")
            return DiagnosisResult(
                task_id=task.task_id,
                layer=task.layer,
                success=False,
                confidence=0.0,
                findings=[f"Analysis failed: {e}"],
                error=str(e),
            )

    def _extract_analysis(
        self,
        messages: list[Any],
        tool_outputs: list[dict],
    ) -> tuple[list[str], float, str | None]:
        """Extract findings, confidence, and root cause from agent output.

        Args:
            messages: Collected agent messages.
            tool_outputs: Collected tool outputs.

        Returns:
            (findings, confidence, root_cause)
        """
        findings = []
        confidence = 0.0
        root_cause = None

        # Look for AI messages with analysis
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                content = msg.content
                if not content:
                    continue

                # Extract findings from structured output
                if "根因" in content or "root cause" in content.lower():
                    root_cause = content
                    confidence = 0.90  # High confidence if root cause identified

                # Look for bullet points or numbered items
                import re
                items = re.findall(r"[-•]\s*(.+?)(?=\n[-•]|\n\n|\Z)", content, re.DOTALL)
                findings.extend([item.strip() for item in items[:10]])

                # Look for confidence mentions
                conf_match = re.search(r"置信度[：:]\s*(\d+(?:\.\d+)?)", content)
                if conf_match:
                    try:
                        confidence = float(conf_match.group(1))
                        if confidence > 1:
                            confidence /= 100  # Convert percentage
                    except ValueError:
                        pass

                if findings or root_cause:
                    break

        # Fallback: extract from tool outputs if no AI analysis
        if not findings and tool_outputs:
            for output in tool_outputs[:5]:
                if isinstance(output, dict):
                    raw = output.get("raw", "")
                    if "route-map" in raw.lower() or "prefix-list" in raw.lower():
                        findings.append(f"Found config: {raw[:200]}...")
                        confidence = max(confidence, 0.70)

        # Auto-detect root cause from policy patterns
        if not root_cause and findings:
            root_cause = self._detect_policy_root_cause(findings, tool_outputs)
            if root_cause:
                confidence = max(confidence, 0.85)

        return findings, confidence, root_cause

    def _detect_policy_root_cause(
        self,
        findings: list[str],
        tool_outputs: list[dict],
    ) -> str | None:
        """Auto-detect root cause from policy configuration patterns.

        Args:
            findings: Extracted findings from AI analysis.
            tool_outputs: Raw tool outputs.

        Returns:
            Root cause description if detected, None otherwise.
        """
        import re

        # Combine all text for pattern matching
        all_text = "\n".join(findings)
        for output in tool_outputs:
            if isinstance(output, dict):
                all_text += "\n" + output.get("raw", "")

        # Pattern 1: route-map with deny clause
        if "route-map" in all_text.lower() and "deny" in all_text.lower():
            # Extract route-map name
            match = re.search(r"route-map\s+(\S+)\s+(?:permit|deny)", all_text)
            if match:
                map_name = match.group(1)
                # Check if it's blocking traffic
                if "deny 20" in all_text or "deny 10" in all_text:
                    return f"BGP route-map '{map_name}' 可能阻止了路由通告 (包含 deny 规则)"

        # Pattern 2: prefix-list not matching target prefix
        prefix_lists = re.findall(
            r"ip prefix-list\s+(\S+)\s+seq\s+\d+\s+permit\s+(\S+)",
            all_text
        )
        if prefix_lists:
            # Check if any prefix-list matches 10.0.0.0/16 or related
            matched_10 = any("10.0" in pl[1] for pl in prefix_lists)
            if not matched_10:
                prefixes = ", ".join(f"{pl[0]}={pl[1]}" for pl in prefix_lists[:3])
                return f"Prefix-list 未包含目标网络: {prefixes} (未匹配 10.0.0.0/16)"

        # Pattern 3: BGP neighbor with route-map
        if "neighbor" in all_text and "route-map" in all_text:
            match = re.search(
                r"neighbor\s+(\S+)\s+route-map\s+(\S+)\s+(in|out)",
                all_text
            )
            if match:
                neighbor, map_name, direction = match.groups()
                return f"BGP 邻居 {neighbor} 应用了 route-map {map_name} ({direction}), 可能过滤了路由"

        return None

    async def verify_config_policy(
        self,
        device: str,
        policy_type: str,
        policy_name: str | None = None,
    ) -> dict[str, Any]:
        """Verify a specific configuration policy on a device.

        Convenience method for common policy verification.

        Args:
            device: Target device hostname.
            policy_type: Type of policy (route-map, prefix-list, acl).
            policy_name: Optional specific policy name to check.

        Returns:
            Dictionary with policy configuration and analysis.
        """
        # Build CLI command based on policy type
        commands = {
            "route-map": f"show run | section route-map{' ' + policy_name if policy_name else ''}",
            "prefix-list": f"show run | section prefix-list{' ' + policy_name if policy_name else ''}",
            "acl": f"show access-list{' ' + policy_name if policy_name else ''}",
        }

        command = commands.get(policy_type)
        if not command:
            return {"error": f"Unknown policy type: {policy_type}"}

        # Execute CLI command
        try:
            from olav.execution.backends.nornir_sandbox import NornirSandbox

            sandbox = NornirSandbox()
            result = await sandbox.execute_cli_show(device, command)

            if not result.success:
                return {"error": result.error, "device": device}

            # Extract and parse the relevant section
            sections = self.config_extractor.extract(result.output, [policy_type])

            return {
                "device": device,
                "policy_type": policy_type,
                "policy_name": policy_name,
                "raw_output": result.output,
                "extracted_config": sections.get(policy_type, ""),
                "success": True,
            }

        except Exception as e:
            return {"error": str(e), "device": device}

    async def execute_from_workflow(
        self,
        query: str,
        target_devices: list[str],
        hypotheses: list[str],
    ) -> DeepAnalyzerResult:
        """Execute Deep Analyzer from ExpertModeWorkflow.

        Wrapper method for integration with ExpertModeWorkflow.
        Converts workflow parameters to internal task format.

        Args:
            query: Original user query.
            target_devices: Devices to investigate.
            hypotheses: Hypotheses from Phase 1 findings.

        Returns:
            DeepAnalyzerResult with aggregated findings.
        """
        all_findings: list[str] = []
        all_tool_outputs: list[dict] = []
        max_confidence = 0.0
        root_cause = None
        root_cause_found = False

        # Build hypothesis string from Phase 1 findings
        hypothesis = "\n".join(hypotheses[:10]) if hypotheses else "Phase 1 未发现明确假设"

        # Create a synthetic task for each investigation focus
        task = DiagnosisTask(
            task_id=0,
            layer="L4",  # Default to L4 for policy verification
            description=f"深度验证: {query}",
            suggested_tables=[],
            suggested_filters={"hostname": target_devices},
        )

        try:
            result = await self.execute(
                task=task,
                phase1_findings=hypotheses,
                hypothesis=hypothesis,
            )

            all_findings.extend(result.findings)
            all_tool_outputs.extend(result.tool_outputs or [])
            max_confidence = max(max_confidence, result.confidence)

            # Check if root cause identified
            for finding in result.findings:
                finding_lower = finding.lower()
                if any(kw in finding_lower for kw in ["根因", "root cause", "确认", "导致"]):
                    root_cause_found = True
                    root_cause = finding
                    break

        except Exception as e:
            logger.exception(f"Deep analysis failed: {e}")
            all_findings.append(f"深度分析失败: {e}")

        return DeepAnalyzerResult(
            success=bool(all_findings),
            confidence=max_confidence,
            findings=all_findings,
            root_cause_found=root_cause_found,
            root_cause=root_cause,
            tool_outputs=all_tool_outputs,
        )
