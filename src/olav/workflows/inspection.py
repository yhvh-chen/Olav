"""Inspection Workflow - Network Inspection with NetBox Sync.

Scope:
- Network state inspection (health checks)
- NetBox SSOT comparison (diff detection)
- Automated reconciliation (with HITL for critical changes)

Tool Chain:
- SuzieQ (network state from Parquet)
- NetBox API (SSOT data)
- DiffEngine (comparison)
- NetBoxReconciler (sync actions)

Workflow:
    User Query ("巡检", "检查同步", "对比NetBox")
    ↓
    [Scope Detection] → Parse device scope from query
    ↓
    [Data Collection] → SuzieQ + NetBox parallel queries
    ↓
    [Diff Analysis] → DiffEngine comparison
    ↓
    [Report Generation] → Markdown report
    ↓
    [Reconciliation] → Auto-correct or HITL pending
    ↓
    [Final Summary]
"""

import sys

if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import logging
from datetime import datetime
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager
from olav.sync import (
    DiffEngine,
    DiffResult,
    EntityType,
    NetBoxReconciler,
    ReconciliationReport,
    ReconcileAction,
)
from olav.sync.rules import get_hitl_summary, requires_hitl_approval
from olav.tools.netbox_tool import NetBoxAPITool
from olav.tools.suzieq_parquet_tool import suzieq_query

from .base import BaseWorkflow, BaseWorkflowState, WorkflowType
from .registry import WorkflowRegistry

logger = logging.getLogger(__name__)


class InspectionState(BaseWorkflowState):
    """State for inspection workflow."""
    
    device_scope: list[str]  # Devices to inspect
    entity_types: list[str]  # Entity types to compare
    diff_report: dict | None  # DiffEngine report
    reconcile_results: list[dict] | None  # Reconciliation results
    dry_run: bool  # Whether to apply changes
    auto_correct: bool  # Whether to auto-correct safe fields
    user_approval: str | None  # HITL approval status: approved/rejected/skip


@WorkflowRegistry.register(
    name="inspection",
    description="网络巡检与 NetBox 同步检查（SuzieQ 采集 → NetBox 对比 → 差异报告 → 自动修正/HITL 审批）",
    examples=[
        "巡检所有核心路由器",
        "检查 R1 R2 的接口状态与 NetBox 是否同步",
        "对比 NetBox 设备清单与实际网络状态",
        "检查 IP 地址分配是否一致",
        "同步 SW1 的接口信息到 NetBox",
        "网络健康检查",
        "执行每日巡检",
        "检查 NetBox 与 SuzieQ 的数据差异",
    ],
    triggers=[
        r"巡检",
        r"inspection",
        r"同步.*netbox",
        r"netbox.*同步",
        r"对比.*netbox",
        r"netbox.*对比",
        r"diff",
        r"reconcil",
        r"健康检查",
        r"health.*check",
    ],
)
class InspectionWorkflow(BaseWorkflow):
    """Inspection workflow with NetBox synchronization."""

    def __init__(self) -> None:
        """Initialize inspection workflow."""
        self.netbox = NetBoxAPITool()
        self.diff_engine = DiffEngine(netbox_tool=self.netbox)
        self.reconciler = NetBoxReconciler(
            netbox_tool=self.netbox,
            diff_engine=self.diff_engine,
            dry_run=True,  # Default to dry run
        )
        self.llm = LLMFactory.get_chat_model()

    @property
    def name(self) -> str:
        return "inspection"

    @property
    def description(self) -> str:
        return "网络巡检与 NetBox SSOT 同步检查"

    @property
    def tools_required(self) -> list[str]:
        return [
            "suzieq_query",
            "suzieq_schema_search",
            "netbox_api",
            "netbox_schema_search",
        ]

    async def validate_input(self, user_query: str) -> tuple[bool, str]:
        """Check if query is about inspection or sync."""
        query_lower = user_query.lower()

        # Match inspection keywords
        inspection_keywords = [
            "巡检",
            "inspection",
            "同步",
            "sync",
            "对比",
            "compare",
            "diff",
            "reconcil",
            "健康检查",
            "health check",
            "netbox",
        ]
        
        if any(kw in query_lower for kw in inspection_keywords):
            return True, "匹配巡检/同步关键词"

        return False, "未匹配巡检关键词"

    def build_graph(self, checkpointer: BaseCheckpointSaver | None = None) -> StateGraph:
        """Build LangGraph for inspection workflow."""
        
        # Define the graph
        workflow = StateGraph(InspectionState)

        # Add nodes
        workflow.add_node("parse_scope", self._parse_scope)
        workflow.add_node("collect_data", self._collect_data)
        workflow.add_node("generate_report", self._generate_report)
        workflow.add_node("hitl_approval", self._hitl_approval)
        workflow.add_node("apply_reconciliation", self._apply_reconciliation)
        workflow.add_node("final_summary", self._final_summary)

        # Define edges
        workflow.set_entry_point("parse_scope")
        workflow.add_edge("parse_scope", "collect_data")
        workflow.add_edge("collect_data", "generate_report")
        workflow.add_edge("generate_report", "hitl_approval")
        workflow.add_conditional_edges(
            "hitl_approval",
            self._route_after_approval,
            {
                "apply_reconciliation": "apply_reconciliation",
                "final_summary": "final_summary",
            },
        )
        workflow.add_edge("apply_reconciliation", "final_summary")
        workflow.add_edge("final_summary", END)

        # Compile - HITL is handled by interrupt() in hitl_approval node
        if checkpointer:
            return workflow.compile(checkpointer=checkpointer)
        return workflow.compile()

    async def _parse_scope(self, state: InspectionState) -> dict[str, Any]:
        """Parse device scope and entity types from user query."""
        messages = state.get("messages", [])
        user_query = messages[-1].content if messages else ""
        
        # Use LLM to extract scope
        system_prompt = """你是网络巡检助手。从用户查询中提取：
1. 设备范围 (device_scope): 具体设备名列表，如 ["R1", "R2"]，如果是"所有"或未指定，返回 ["all"]
2. 检查类型 (entity_types): 要检查的实体类型列表，可选: interface, ip_address, device, vlan

以 JSON 格式返回，例如:
{"device_scope": ["R1", "R2"], "entity_types": ["interface", "ip_address"]}

如果用户未指定，默认返回:
{"device_scope": ["all"], "entity_types": ["interface", "ip_address", "device"]}
"""
        
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_query),
            ])
            
            import json
            # Extract JSON from response
            content = response.content
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(content[start:end])
                device_scope = parsed.get("device_scope", ["all"])
                entity_types = parsed.get("entity_types", ["interface", "ip_address", "device"])
            else:
                device_scope = ["all"]
                entity_types = ["interface", "ip_address", "device"]
                
        except Exception as e:
            logger.warning(f"Failed to parse scope with LLM: {e}")
            device_scope = ["all"]
            entity_types = ["interface", "ip_address", "device"]
        
        # If "all", query NetBox for device list
        if device_scope == ["all"]:
            try:
                result = await self.netbox.execute(
                    path="/api/dcim/devices/",
                    method="GET",
                    params={"limit": 50},
                )
                # result.data is a list from NetBoxAdapter
                if not result.error and result.data:
                    device_scope = [d["name"] for d in result.data if isinstance(d, dict) and "name" in d]
                else:
                    device_scope = []
            except Exception as e:
                logger.error(f"Failed to get device list from NetBox: {e}")
                device_scope = []
        
        # Resolve entity type enums
        type_map = {
            "interface": EntityType.INTERFACE,
            "ip_address": EntityType.IP_ADDRESS,
            "device": EntityType.DEVICE,
            "vlan": EntityType.VLAN,
        }
        resolved_types = [type_map[t] for t in entity_types if t in type_map]
        
        return {
            "device_scope": device_scope,
            "entity_types": [t.value for t in resolved_types],
            "dry_run": state.get("dry_run", True),
            "auto_correct": state.get("auto_correct", True),
        }

    async def _collect_data(self, state: InspectionState) -> dict[str, Any]:
        """Collect data from SuzieQ and NetBox, run DiffEngine."""
        device_scope = state.get("device_scope", [])
        entity_types_str = state.get("entity_types", ["interface", "ip_address", "device"])
        
        if not device_scope:
            return {
                "diff_report": None,
                "messages": state["messages"] + [
                    AIMessage(content="⚠️ 未找到设备，无法执行巡检。请检查 NetBox 设备清单。")
                ],
            }
        
        # Convert string back to EntityType
        type_map = {
            "interface": EntityType.INTERFACE,
            "ip_address": EntityType.IP_ADDRESS,
            "device": EntityType.DEVICE,
            "vlan": EntityType.VLAN,
        }
        entity_types = [type_map[t] for t in entity_types_str if t in type_map]
        
        # Run DiffEngine comparison
        try:
            report = await self.diff_engine.compare_all(
                devices=device_scope,
                entity_types=entity_types,
            )
            
            return {
                "diff_report": report.to_dict(),
            }
            
        except Exception as e:
            logger.error(f"DiffEngine comparison failed: {e}")
            return {
                "diff_report": None,
                "messages": state["messages"] + [
                    AIMessage(content=f"❌ 数据对比失败: {str(e)}")
                ],
            }

    async def _generate_report(self, state: InspectionState) -> dict[str, Any]:
        """Generate inspection report."""
        diff_report_dict = state.get("diff_report")
        
        if not diff_report_dict:
            return {}
        
        # Reconstruct report for markdown generation
        report = ReconciliationReport(
            device_scope=diff_report_dict.get("device_scope", []),
            total_entities=diff_report_dict.get("total_entities", 0),
            matched=diff_report_dict.get("matched", 0),
            mismatched=diff_report_dict.get("mismatched", 0),
            missing_in_netbox=diff_report_dict.get("missing_in_netbox", 0),
            missing_in_network=diff_report_dict.get("missing_in_network", 0),
            summary_by_type=diff_report_dict.get("summary_by_type", {}),
            summary_by_severity=diff_report_dict.get("summary_by_severity", {}),
        )
        
        # Reconstruct diffs
        for diff_dict in diff_report_dict.get("diffs", []):
            report.diffs.append(DiffResult.from_dict(diff_dict))
        
        markdown_report = report.to_markdown()
        
        return {
            "messages": state["messages"] + [
                AIMessage(content=f"📋 **巡检报告生成完成**\n\n{markdown_report}")
            ],
        }

    async def _hitl_approval(self, state: InspectionState) -> dict[str, Any]:
        """HITL approval for sync operations.
        
        Uses LangGraph interrupt to pause and wait for user approval.
        """
        from langgraph.types import interrupt
        from config.settings import AgentConfig
        
        diff_report_dict = state.get("diff_report")
        user_approval = state.get("user_approval")
        
        # Check if there are any diffs to sync
        if not diff_report_dict or not diff_report_dict.get("diffs"):
            return {
                "user_approval": "skip",
                "dry_run": True,  # No sync needed
            }
        
        diff_count = len(diff_report_dict.get("diffs", []))
        mismatched = diff_report_dict.get("mismatched", 0)
        
        # If no mismatches, skip HITL
        if mismatched == 0:
            return {
                "user_approval": "skip",
                "dry_run": True,
            }
        
        # YOLO mode: auto-approve
        if AgentConfig.YOLO_MODE and user_approval is None:
            logger.info("[YOLO] Auto-approving inspection sync...")
            return {
                "user_approval": "approved",
                "dry_run": False,  # Execute actual sync
            }
        
        # Already processed (resuming after interrupt)
        if user_approval in ("approved", "rejected", "skip"):
            return {
                "user_approval": user_approval,
                "dry_run": user_approval != "approved",
            }
        
        # HITL: Request user approval via interrupt
        summary = diff_report_dict.get("summary_by_severity", {})
        
        approval_message = (
            f"🔍 **巡检发现 {mismatched} 处差异需要同步**\n\n"
            f"- 严重: {summary.get('critical', 0)}\n"
            f"- 警告: {summary.get('warning', 0)}\n"
            f"- 信息: {summary.get('info', 0)}\n\n"
            f"是否将网络状态同步到 NetBox？\n"
            f"输入 Y 确认执行, N 取消:"
        )
        
        approval_response = interrupt({
            "action": "approval_required",
            "diff_count": diff_count,
            "mismatched": mismatched,
            "summary": summary,
            "message": approval_message,
        })
        
        # Process approval response
        if isinstance(approval_response, dict):
            if approval_response.get("approved") or approval_response.get("user_approval") == "approved":
                return {
                    "user_approval": "approved",
                    "dry_run": False,  # Execute actual sync
                }
            else:
                return {
                    "user_approval": "rejected",
                    "dry_run": True,  # Don't execute
                }
        else:
            # String response - check for approval
            return {
                "user_approval": "approved" if approval_response else "rejected",
                "dry_run": not bool(approval_response),
            }

    def _route_after_approval(self, state: InspectionState) -> Literal["apply_reconciliation", "final_summary"]:
        """Route based on approval decision."""
        user_approval = state.get("user_approval")
        
        if user_approval == "approved":
            return "apply_reconciliation"
        # Skip or rejected - go directly to summary
        return "final_summary"

    async def _apply_reconciliation(self, state: InspectionState) -> dict[str, Any]:
        """Apply reconciliation for auto-correctable diffs."""
        diff_report_dict = state.get("diff_report")
        dry_run = state.get("dry_run", True)
        auto_correct = state.get("auto_correct", True)
        
        if not diff_report_dict or not diff_report_dict.get("diffs"):
            return {"reconcile_results": []}
        
        # Reconstruct report
        report = ReconciliationReport(
            device_scope=diff_report_dict.get("device_scope", []),
        )
        for diff_dict in diff_report_dict.get("diffs", []):
            report.diffs.append(DiffResult.from_dict(diff_dict))
        
        # Configure reconciler
        self.reconciler.dry_run = dry_run
        
        # User already approved at workflow level, so no need for per-item HITL
        # require_hitl=False means execute directly after user approval
        user_approved = state.get("user_approval") == "approved"
        
        # Run reconciliation
        try:
            results = await self.reconciler.reconcile(
                report,
                auto_correct=auto_correct,
                require_hitl=not user_approved,  # Skip per-item HITL if user already approved
            )
            
            return {
                "reconcile_results": [r.to_dict() for r in results],
            }
            
        except Exception as e:
            logger.error(f"Reconciliation failed: {e}")
            return {
                "reconcile_results": [],
                "messages": state["messages"] + [
                    AIMessage(content=f"⚠️ 同步操作失败: {str(e)}")
                ],
            }

    async def _final_summary(self, state: InspectionState) -> dict[str, Any]:
        """Generate final summary."""
        reconcile_results = state.get("reconcile_results", [])
        diff_report = state.get("diff_report", {})
        dry_run = state.get("dry_run", True)
        
        # Count actions
        action_counts = {}
        for result in reconcile_results:
            action = result.get("action", "unknown")
            action_counts[action] = action_counts.get(action, 0) + 1
        
        # Build summary
        summary_lines = [
            "## 🔍 巡检总结",
            "",
            f"- **检查设备**: {len(diff_report.get('device_scope', []))} 台",
            f"- **总实体数**: {diff_report.get('total_entities', 0)}",
            f"- **匹配**: {diff_report.get('matched', 0)}",
            f"- **差异**: {diff_report.get('mismatched', 0)}",
            "",
            "### 同步操作结果" + (" (Dry Run)" if dry_run else ""),
        ]
        
        action_emoji = {
            "auto_corrected": "✅",
            "hitl_pending": "⏳",
            "hitl_approved": "✅",
            "hitl_rejected": "❌",
            "report_only": "📝",
            "skipped": "⏭️",
            "error": "❌",
        }
        
        for action, count in action_counts.items():
            emoji = action_emoji.get(action, "")
            summary_lines.append(f"- {emoji} {action}: {count}")
        
        if not action_counts:
            summary_lines.append("- 无需同步操作")
        
        # HITL pending items
        hitl_pending = [r for r in reconcile_results if r.get("action") == "hitl_pending"]
        if hitl_pending:
            summary_lines.extend([
                "",
                "### ⏳ 待 HITL 审批",
            ])
            for r in hitl_pending[:5]:  # Show top 5
                diff = r.get("diff", {})
                summary_lines.append(
                    f"- {diff.get('device')}/{diff.get('field')}: "
                    f"{diff.get('netbox_value')} → {diff.get('network_value')}"
                )
            if len(hitl_pending) > 5:
                summary_lines.append(f"  ... 及其他 {len(hitl_pending) - 5} 项")
        
        summary = "\n".join(summary_lines)
        
        return {
            "messages": state["messages"] + [
                AIMessage(content=summary)
            ],
        }


async def run_inspection(
    devices: list[str] | None = None,
    entity_types: list[str] | None = None,
    dry_run: bool = True,
    auto_correct: bool = True,
) -> tuple[ReconciliationReport, list[dict]]:
    """
    Convenience function to run inspection directly.
    
    Args:
        devices: Device list (None = all from NetBox)
        entity_types: Entity types to check
        dry_run: If True, don't make actual changes
        auto_correct: Apply auto-corrections for safe fields
        
    Returns:
        Tuple of (report, reconcile_results)
    """
    workflow = InspectionWorkflow()
    workflow.reconciler.dry_run = dry_run
    
    # Get devices from NetBox if not specified
    if devices is None:
        result = await workflow.netbox.execute(
            path="/api/dcim/devices/",
            method="GET",
            params={"limit": 50},
        )
        if not result.error and result.data.get("results"):
            devices = [d["name"] for d in result.data["results"]]
        else:
            devices = []
    
    # Default entity types
    if entity_types is None:
        entity_types = [EntityType.INTERFACE, EntityType.IP_ADDRESS, EntityType.DEVICE]
    else:
        type_map = {
            "interface": EntityType.INTERFACE,
            "ip_address": EntityType.IP_ADDRESS,
            "device": EntityType.DEVICE,
            "vlan": EntityType.VLAN,
        }
        entity_types = [type_map.get(t, EntityType.INTERFACE) for t in entity_types]
    
    # Run comparison
    report = await workflow.diff_engine.compare_all(
        devices=devices,
        entity_types=entity_types,
    )
    
    # Run reconciliation
    results = await workflow.reconciler.reconcile(
        report,
        auto_correct=auto_correct,
        require_hitl=True,
    )
    
    return report, [r.to_dict() for r in results]
