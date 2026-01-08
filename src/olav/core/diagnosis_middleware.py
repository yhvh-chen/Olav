"""Diagnosis Approval Middleware for Phase 4.1.

This middleware implements HITL (Human-in-the-Loop) approval between
macro-analysis and micro-analysis phases.

Workflow:
1. Macro-analysis completes
2. Middleware pauses execution
3. Presents micro-analysis plan to user (Markdown formatted)
4. User can: approve / modify / cancel
5. If approved: proceed to micro-analysis
6. If modified: use modified plan
7. If canceled: stop and return macro-analysis results
"""

from typing import Any

from olav.core.settings import OlavSettings


class DiagnosisApprovalMiddleware:
    """Middleware for HITL approval between macro and micro analysis.

    This middleware intercepts the agent execution after macro-analysis
    completes and presents a micro-analysis plan for user approval.
    """

    def __init__(
        self,
        settings_path: str | None = None,
        project_root: str | None = None,
    ) -> None:
        """Initialize diagnosis approval middleware.

        Args:
            settings_path: Optional path to settings file
            project_root: Optional project root directory
        """
        self.settings = OlavSettings(
            settings_path=settings_path, project_root=project_root
        )
        self._approval_pending = False
        self._current_plan = None

    def should_interrupt_after_macro(
        self, macro_result: dict[str, Any], confidence: float | None = None
    ) -> bool:
        """Check if execution should pause after macro-analysis.

        Args:
            macro_result: Result from macro-analysis
            confidence: Confidence score (0-1) if available

        Returns:
            True if should pause for approval, False otherwise
        """
        # Check if approval is required
        if not self.settings.diagnosis_require_approval:
            return False

        # Check auto-approval threshold
        if confidence is not None:
            threshold = self.settings.diagnosis_auto_approve_threshold
            if confidence < threshold:
                # Low confidence: auto-approve micro-analysis
                return False

        # High confidence or no confidence score: require approval
        return True

    def generate_micro_analysis_plan(
        self, macro_result: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate micro-analysis plan based on macro-analysis results.

        Args:
            macro_result: Results from macro-analysis

        Returns:
            Micro-analysis plan dictionary
        """
        # Extract key findings from macro-analysis
        findings = macro_result.get("findings", [])
        suspected_devices = macro_result.get("suspected_devices", [])
        suspected_layers = macro_result.get("suspected_layers", [])
        macro_result.get("next_steps", [])

        # Generate structured plan
        plan = {
            "macro_summary": macro_result.get("summary", "Macro analysis completed"),
            "findings": findings,
            "suspected_devices": suspected_devices,
            "suspected_layers": suspected_layers,
            "micro_analysis_tasks": self._generate_micro_tasks(
                suspected_devices, suspected_layers
            ),
            "estimated_duration": self._estimate_duration(suspected_devices, suspected_layers),
            "confidence": macro_result.get("confidence", 0.5),
        }

        self._current_plan = plan
        return plan

    def _generate_micro_tasks(
        self, devices: list[str], layers: list[str]
    ) -> list[dict[str, Any]]:
        """Generate specific micro-analysis tasks.

        Args:
            devices: Suspected devices
            layers: Suspected TCP/IP layers

        Returns:
            List of micro-analysis tasks
        """
        tasks = []

        # Map layers to specific checks
        layer_checks = {
            "physical": [
                "Check interface status (show interfaces status)",
                "Check optical power (show interfaces transceiver)",
                "Check error counters (show interfaces counters errors)",
            ],
            "datalink": [
                "Check VLAN configuration (show vlan brief)",
                "Check MAC address table (show mac address-table)",
                "Check STP state (show spanning-tree)",
            ],
            "network": [
                "Check IP addresses (show ip interface brief)",
                "Check routing table (show ip route)",
                "Check ARP table (show ip arp)",
            ],
            "transport": [
                "Check ACL configuration (show access-lists)",
                "Check NAT translations (show ip nat translations)",
            ],
        }

        # Generate tasks for each device-layer combination
        for device in devices:
            for layer in layers:
                if layer.lower() in layer_checks:
                    tasks.append({
                        "device": device,
                        "layer": layer,
                        "checks": layer_checks[layer.lower()],
                    })

        # Default tasks if no specific layers identified
        if not tasks:
            for device in devices:
                tasks.append({
                    "device": device,
                    "layer": "all",
                    "checks": [
                        "System health (show version, show processes cpu)",
                        "Interface status (show interfaces status)",
                        "Routing status (show ip route summary)",
                        "Protocol neighbors (show ip ospf neighbor, show ip bgp summary)",
                    ],
                })

        return tasks

    def _estimate_duration(
        self, devices: list[str], layers: list[str]
    ) -> str:
        """Estimate micro-analysis duration.

        Args:
            devices: Number of devices
            layers: Number of layers

        Returns:
            Estimated duration as string
        """
        # Rough estimate: 5 minutes per device-layer combination
        tasks = len(devices) * max(len(layers), 1)
        minutes = tasks * 5

        if minutes < 15:
            return f"{minutes} minutes"
        elif minutes < 60:
            return f"{minutes} minutes (~{minutes // 5} tasks)"
        else:
            hours = minutes // 60
            remain = minutes % 60
            return f"{hours}h {remain}m"

    def format_plan_for_approval(self, plan: dict[str, Any]) -> str:
        """Format micro-analysis plan as Markdown for user approval.

        Args:
            plan: Micro-analysis plan

        Returns:
            Formatted Markdown string
        """
        lines = []
        lines.append("# 🔍 微观分析计划 - 待您审批")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Summary
        lines.append("## 📊 宏观分析总结")
        lines.append("")
        lines.append(plan["macro_summary"])
        lines.append("")

        # Findings
        if plan["findings"]:
            lines.append("### 关键发现")
            lines.append("")
            for i, finding in enumerate(plan["findings"], 1):
                lines.append(f"{i}. {finding}")
            lines.append("")

        # Suspected devices
        if plan["suspected_devices"]:
            lines.append("### 🔧 待检查设备")
            lines.append("")
            for device in plan["suspected_devices"]:
                lines.append(f"- `{device}`")
            lines.append("")

        # Suspected layers
        if plan["suspected_layers"]:
            lines.append("### 📚 待检查层级")
            lines.append("")
            for layer in plan["suspected_layers"]:
                lines.append(f"- **{layer}**")
            lines.append("")

        # Micro-analysis tasks
        lines.append("## 📋 微观分析任务")
        lines.append("")
        for i, task in enumerate(plan["micro_analysis_tasks"], 1):
            lines.append(f"### 任务 {i}: {task['device']} - {task['layer']}")
            lines.append("")
            for check in task["checks"]:
                lines.append(f"- [ ] {check}")
            lines.append("")

        # Duration and confidence
        lines.append("---")
        lines.append("")
        lines.append(
            f"⏱️ **预计耗时**: {plan['estimated_duration']}  |  "
            f"🎯 **置信度**: {int(plan['confidence'] * 100)}%"
        )
        lines.append("")
        lines.append("## ✋ 待您操作")
        lines.append("")
        lines.append("请选择:")
        lines.append("1. **批准** - 按原计划执行微观分析")
        lines.append("2. **修改** - 调整计划后执行")
        lines.append("3. **取消** - 仅使用宏观分析结果")
        lines.append("")
        lines.append("---")

        return "\n".join(lines)

    def handle_user_response(
        self, response: str, plan: dict[str, Any]
    ) -> tuple[bool, dict[str, Any] | None]:
        """Handle user response to approval request.

        Args:
            response: User's response (approve/modify/cancel)
            plan: Current micro-analysis plan

        Returns:
            Tuple of (should_proceed, modified_plan)
            - should_proceed: True if should continue to micro-analysis
            - modified_plan: Updated plan if user modified, None if canceled
        """
        response_lower = response.lower().strip()

        # Check for approval
        approve_words = ["批准", "approve", "同意", "ok", "好的", "继续"]
        if any(word in response_lower for word in approve_words):
            return True, plan

        # Check for cancellation
        cancel_words = ["取消", "cancel", "停止", "不要", "no"]
        if any(word in response_lower for word in cancel_words):
            return False, None

        # Check for modification
        if any(word in response_lower for word in ["修改", "modify", "调整", "change"]):
            # Parse modifications from response
            modified_plan = self._parse_modifications(response, plan)
            return True, modified_plan

        # Default: ask for clarification
        return False, None

    def _parse_modifications(
        self, response: str, plan: dict[str, Any]
    ) -> dict[str, Any]:
        """Parse user modifications to the plan.

        Args:
            response: User's modification request
            plan: Current plan

        Returns:
            Modified plan
        """
        # Start with current plan
        modified = plan.copy()

        # Parse device list modifications
        # TODO: Implement NLP-based parsing

        # For now, return plan unchanged
        # In production, would use LLM to parse user's modifications
        return modified

    def create_interrupt_state(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Create interrupt state for HITL approval.

        Args:
            plan: Micro-analysis plan

        Returns:
            Interrupt state dictionary
        """
        return {
            "type": "diagnosis_approval",
            "plan": plan,
            "formatted_plan": self.format_plan_for_approval(plan),
            "timestamp": None,  # Will be set by framework
        }

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"DiagnosisApprovalMiddleware("
            f"require_approval={self.settings.diagnosis_require_approval}, "
            f"auto_approve_threshold={self.settings.diagnosis_auto_approve_threshold}"
            f")"
        )


__all__ = ["DiagnosisApprovalMiddleware"]
