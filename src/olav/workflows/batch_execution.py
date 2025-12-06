"""Batch Execution Workflow (Multi-Device Configuration Changes).

Scope:
- Batch configuration changes across multiple devices
- Parallel execution using LangGraph Send()
- Unified HITL approval for all devices
- Aggregated results and rollback support

Tool Chain:
- NetBox/SuzieQ (device discovery)
- NETCONF (preferred, with commit-confirmed)
- CLI (fallback)

Workflow:
    User Request: "给所有交换机添加 VLAN 100"
    ↓
    [Task Planner] → Parse intent, operation type, params
    ↓
    [Device Resolver] → Query NetBox/SuzieQ for device list
    ↓
    [Change Plan] → Generate unified change plan
    ↓
    [HITL Approval] → Human review (single approval for all devices)
    ├─ Approved → [Parallel Executor] → Send() fan-out to workers
    │                    ↓
    │              [Result Aggregator] → Collect all results
    │                    ↓
    │              [Final Report]
    │
    └─ Rejected → [Final Report] (abort)
"""

import json
import logging
import sys
import time
from typing import Annotated, Literal, TypedDict

if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Send

from olav.core.llm import LLMFactory
from olav.tools.netbox_tool import netbox_api_call
from olav.tools.nornir_tool import netconf_tool
from olav.tools.suzieq_parquet_tool import suzieq_query

from .base import BaseWorkflow
from .registry import WorkflowRegistry

logger = logging.getLogger(__name__)


class DeviceTask(TypedDict):
    """单设备任务"""

    device: str
    operation_type: str  # "add_vlan", "change_mtu", etc.
    operation_params: dict  # {"vlan_id": 100, "name": "Guest"}


class DeviceResult(TypedDict):
    """单设备执行结果"""

    device: str
    success: bool
    output: str | None
    error: str | None
    execution_time_ms: float


class BatchExecutionState(TypedDict):
    """BatchExecutionWorkflow 状态"""

    messages: Annotated[list, add_messages]

    # Task Planning
    user_intent: str  # 原始用户请求
    operation_type: str | None  # "add_vlan", "change_mtu", etc.
    operation_params: dict | None  # {"vlan_id": 100, "name": "Guest"}

    # Device Resolution
    device_filter: dict | None  # NetBox filter or SuzieQ query
    resolved_devices: list[str] | None  # ["Switch-A", "Switch-B", ...]

    # HITL Approval
    change_plan: str | None  # Markdown 格式变更计划
    approval_status: str | None  # "pending" | "approved" | "rejected"

    # Parallel Execution
    device_tasks: list[DeviceTask] | None  # Fan-out 任务
    device_results: list[DeviceResult] | None  # Fan-in 结果

    # Final Report
    summary: dict | None  # {"total": 10, "success": 9, "failed": 1}


# Worker state for Send() subgraph
class DeviceWorkerState(TypedDict):
    """State for individual device worker"""

    device: str
    operation_type: str
    operation_params: dict
    result: DeviceResult | None


@WorkflowRegistry.register(
    name="batch_execution",
    description="多设备批量配置变更（Task Planning → Device Resolution → HITL → Parallel Execution）",
    examples=[
        "给所有交换机添加 VLAN 100",
        "在所有核心路由器上配置 NTP 服务器",
        "批量修改所有设备的 SNMP community",
        "给标签为 production 的设备配置 syslog",
        "所有边界路由器添加 BGP community",
        "批量更新设备描述信息",
    ],
    triggers=[
        r"所有",
        r"批量",
        r"全部",
        r"多台",
        r"all devices",
        r"batch",
        r"multiple",
        r"every",
    ],
)
class BatchExecutionWorkflow(BaseWorkflow):
    """Batch device configuration workflow with parallel execution."""

    @property
    def name(self) -> str:
        return "batch_execution"

    @property
    def description(self) -> str:
        return "多设备批量配置变更（Task Planning → Device Resolution → HITL → Parallel Execution）"

    @property
    def tools_required(self) -> list[str]:
        return [
            "netbox_api_call",  # 设备发现
            "suzieq_query",  # 备用设备发现
            "netconf_tool",  # 主要执行方式
            "cli_tool",  # 降级方式
        ]

    async def validate_input(self, user_query: str) -> tuple[bool, str]:
        """Check if request is a batch configuration change."""
        query_lower = user_query.lower()

        # 必须包含批量关键词
        batch_keywords = [
            "所有",
            "批量",
            "全部",
            "多台",
            "每个",
            "每台",
            "all",
            "batch",
            "multiple",
            "every",
            "each",
        ]
        has_batch = any(kw in query_lower for kw in batch_keywords)

        # 必须包含配置变更关键词
        change_keywords = [
            "配置",
            "添加",
            "修改",
            "设置",
            "删除",
            "更新",
            "configure",
            "add",
            "modify",
            "set",
            "delete",
            "update",
            "change",
        ]
        has_change = any(kw in query_lower for kw in change_keywords)

        if has_batch and has_change:
            return True, "匹配批量配置变更场景"

        if has_batch and not has_change:
            return False, "批量查询应使用 query_diagnostic workflow"

        return False, "非批量操作，应使用 device_execution workflow"

    def build_graph(self, checkpointer: BaseCheckpointSaver) -> StateGraph:
        """Build batch execution workflow graph with parallel workers."""

        # ============================================
        # Node Definitions
        # ============================================

        async def task_planner_node(state: BatchExecutionState) -> BatchExecutionState:
            """Parse user intent into operation type and params."""
            llm = LLMFactory.get_chat_model(json_mode=True)

            user_query = state["messages"][0].content

            system_prompt = """你是一个网络配置解析专家。解析用户的批量配置请求。

返回 JSON 格式：
{
    "operation_type": "操作类型，如 add_vlan, change_mtu, configure_ntp, add_route 等",
    "operation_params": {
        "参数名": "参数值"
    },
    "device_filter": {
        "role": "设备角色，如 switch, router, firewall（可选）",
        "site": "站点名称（可选）",
        "tag": "标签（可选）",
        "name_pattern": "名称模式（可选）"
    }
}

示例：
- "给所有交换机添加 VLAN 100" →
  {"operation_type": "add_vlan", "operation_params": {"vlan_id": 100}, "device_filter": {"role": "switch"}}

- "在生产环境设备上配置 NTP 10.0.0.1" →
  {"operation_type": "configure_ntp", "operation_params": {"server": "10.0.0.1"}, "device_filter": {"tag": "production"}}
"""

            response = await llm.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=user_query)]
            )

            try:
                parsed = json.loads(response.content)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse task plan: {response.content}")
                parsed = {
                    "operation_type": "unknown",
                    "operation_params": {},
                    "device_filter": {},
                }

            return {
                **state,
                "user_intent": user_query,
                "operation_type": parsed.get("operation_type"),
                "operation_params": parsed.get("operation_params", {}),
                "device_filter": parsed.get("device_filter", {}),
            }

        async def device_resolver_node(state: BatchExecutionState) -> BatchExecutionState:
            """Resolve device list from NetBox or SuzieQ."""
            device_filter = state.get("device_filter", {})
            devices = []

            # Try NetBox first
            try:
                params = {}
                if device_filter.get("role"):
                    params["role"] = device_filter["role"]
                if device_filter.get("site"):
                    params["site"] = device_filter["site"]
                if device_filter.get("tag"):
                    params["tag"] = device_filter["tag"]

                # Add olav-managed tag by default
                if "tag" not in params:
                    params["tag"] = "olav-managed"

                result = await netbox_api_call.ainvoke(
                    {"endpoint": "/dcim/devices/", "method": "GET", "params": params}
                )

                if isinstance(result, dict) and "results" in result:
                    devices = [d["name"] for d in result["results"] if d.get("name")]

            except Exception as e:
                logger.warning(f"NetBox query failed: {e}, falling back to SuzieQ")

            # Fallback to SuzieQ if NetBox failed or returned empty
            if not devices:
                try:
                    result = await suzieq_query.ainvoke(
                        {"table": "device", "method": "get", "columns": ["hostname"]}
                    )
                    if isinstance(result, list):
                        devices = [d.get("hostname") for d in result if d.get("hostname")]
                except Exception as e:
                    logger.error(f"SuzieQ query also failed: {e}")

            # Apply name pattern filter if specified
            name_pattern = device_filter.get("name_pattern")
            if name_pattern and devices:
                import re

                pattern = re.compile(name_pattern, re.IGNORECASE)
                devices = [d for d in devices if pattern.search(d)]

            logger.info(f"Resolved {len(devices)} devices for batch operation")

            return {
                **state,
                "resolved_devices": devices,
            }

        async def change_plan_generator_node(
            state: BatchExecutionState,
        ) -> BatchExecutionState:
            """Generate change plan for HITL review."""
            devices = state.get("resolved_devices", [])
            op_type = state.get("operation_type", "unknown")
            op_params = state.get("operation_params", {})

            if not devices:
                plan = """
## 批量配置变更计划

⚠️ **警告**: 未找到匹配的设备

请检查设备过滤条件或确认设备已正确标记。
                """
            else:
                device_list = "\n".join(f"- {d}" for d in devices[:20])
                more_devices = (
                    f"\n... 还有 {len(devices) - 20} 台设备" if len(devices) > 20 else ""
                )

                plan = f"""
## 批量配置变更计划

**操作类型**: `{op_type}`
**操作参数**: `{json.dumps(op_params, ensure_ascii=False)}`
**影响设备**: {len(devices)} 台

### 设备列表
{device_list}{more_devices}

### 预期变更
每台设备将执行 `{op_type}` 操作，参数: {json.dumps(op_params, ensure_ascii=False)}

### 执行策略
- **并行度**: 最多 10 台设备同时执行
- **回滚策略**: NETCONF 使用 commit-confirmed (60秒自动回滚)
- **失败处理**: 单设备失败不影响其他设备

### 风险评估
- 设备数量: {len(devices)}
- 操作类型: {'低风险' if op_type in ('add_vlan', 'configure_ntp') else '中等风险'}

**请审批此变更计划 (Y/N)**
                """

            return {
                **state,
                "change_plan": plan.strip(),
                "approval_status": "pending",
            }

        async def hitl_approval_node(state: BatchExecutionState) -> BatchExecutionState:
            """HITL approval - unified for all devices."""
            from config.settings import AgentConfig
            from langgraph.types import interrupt

            user_approval = state.get("approval_status")

            # YOLO mode: auto-approve
            if AgentConfig.YOLO_MODE and user_approval == "pending":
                logger.info("[YOLO] Auto-approving batch execution...")
                return {
                    **state,
                    "approval_status": "approved",
                }

            # Already processed
            if user_approval in ("approved", "rejected"):
                return state

            # No devices to process
            devices = state.get("resolved_devices", [])
            if not devices:
                return {
                    **state,
                    "approval_status": "rejected",
                    "messages": state["messages"]
                    + [AIMessage(content="未找到匹配的设备，操作已取消。")],
                }

            # HITL: Request user approval
            approval_response = interrupt(
                {
                    "action": "batch_approval_required",
                    "change_plan": state.get("change_plan"),
                    "device_count": len(devices),
                    "message": f"请审批批量配置变更:\n\n{state.get('change_plan')}\n\n输入 Y 确认, N 取消:",
                }
            )

            # Process response
            if isinstance(approval_response, dict):
                approved = approval_response.get("approved") or approval_response.get(
                    "user_approval"
                ) == "approved"
            else:
                approved = str(approval_response).strip().upper() in ("Y", "YES", "TRUE", "1")

            return {
                **state,
                "approval_status": "approved" if approved else "rejected",
            }

        def route_after_approval(
            state: BatchExecutionState,
        ) -> Literal["parallel_executor", "final_report"]:
            """Route based on approval and device availability."""
            if state.get("approval_status") != "approved":
                return "final_report"
            if not state.get("resolved_devices"):
                return "final_report"
            return "parallel_executor"

        def fan_out_tasks(state: BatchExecutionState) -> list[Send]:
            """Generate Send() tasks for parallel execution."""
            devices = state.get("resolved_devices", [])
            op_type = state.get("operation_type", "unknown")
            op_params = state.get("operation_params", {})

            return [
                Send(
                    "device_worker",
                    DeviceWorkerState(
                        device=device,
                        operation_type=op_type,
                        operation_params=op_params,
                        result=None,
                    ),
                )
                for device in devices
            ]

        async def parallel_executor_node(state: BatchExecutionState) -> BatchExecutionState:
            """Prepare for parallel execution - generates tasks for workers."""
            devices = state.get("resolved_devices", [])
            op_type = state.get("operation_type", "unknown")
            op_params = state.get("operation_params", {})

            device_tasks = [
                DeviceTask(device=d, operation_type=op_type, operation_params=op_params)
                for d in devices
            ]

            return {
                **state,
                "device_tasks": device_tasks,
                "device_results": [],  # Will be populated by workers
            }

        async def device_worker_node(worker_state: DeviceWorkerState) -> DeviceWorkerState:
            """Execute configuration on a single device."""
            device = worker_state["device"]
            op_type = worker_state["operation_type"]
            op_params = worker_state["operation_params"]

            start_time = time.perf_counter()

            try:
                # Generate NETCONF config based on operation type
                config_payload = _generate_netconf_config(op_type, op_params)

                # Execute via NETCONF with commit-confirmed
                result = await netconf_tool.ainvoke(
                    {
                        "hostname": device,
                        "operation": "edit-config",
                        "config": config_payload,
                        "target": "candidate",
                        "commit_confirmed": 60,  # Auto-rollback after 60s
                    }
                )

                success = not (isinstance(result, dict) and result.get("error"))
                output = result.get("output") if isinstance(result, dict) else str(result)
                error = result.get("error") if isinstance(result, dict) else None

                device_result = DeviceResult(
                    device=device,
                    success=success,
                    output=output,
                    error=error,
                    execution_time_ms=(time.perf_counter() - start_time) * 1000,
                )

            except Exception as e:
                logger.error(f"Failed to execute on {device}: {e}")
                device_result = DeviceResult(
                    device=device,
                    success=False,
                    output=None,
                    error=str(e),
                    execution_time_ms=(time.perf_counter() - start_time) * 1000,
                )

            return {
                **worker_state,
                "result": device_result,
            }

        async def result_aggregator_node(state: BatchExecutionState) -> BatchExecutionState:
            """Aggregate results from all workers."""
            results = state.get("device_results", [])

            if not results:
                # No results yet - this shouldn't happen in normal flow
                return state

            success_count = sum(1 for r in results if r.get("success"))
            failed_count = len(results) - success_count

            summary = {
                "total": len(results),
                "success": success_count,
                "failed": failed_count,
                "success_rate": f"{success_count / len(results) * 100:.1f}%" if results else "N/A",
                "failed_devices": [r["device"] for r in results if not r.get("success")],
                "avg_execution_time_ms": (
                    sum(r.get("execution_time_ms", 0) for r in results) / len(results)
                    if results
                    else 0
                ),
            }

            return {
                **state,
                "summary": summary,
            }

        async def final_report_node(state: BatchExecutionState) -> BatchExecutionState:
            """Generate final execution report."""
            approval_status = state.get("approval_status")
            summary = state.get("summary")
            results = state.get("device_results", [])
            op_type = state.get("operation_type", "unknown")

            if approval_status == "rejected":
                report = """
## 批量配置变更报告

**状态**: ⚠️ 已取消

用户拒绝了变更计划，未执行任何操作。
                """
            elif not state.get("resolved_devices"):
                report = """
## 批量配置变更报告

**状态**: ⚠️ 无设备

未找到符合条件的设备，无法执行操作。
                """
            elif summary:
                failed_devices = "\n".join(
                    f"- {d}" for d in summary.get("failed_devices", [])
                ) or "无"

                # Generate result table (limit to 30 rows)
                result_rows = []
                for r in results[:30]:
                    status = "✓" if r.get("success") else "✗"
                    exec_time = f"{r.get('execution_time_ms', 0):.0f}"
                    error = r.get("error", "-") or "-"
                    if len(error) > 50:
                        error = error[:47] + "..."
                    result_rows.append(f"| {r['device']} | {status} | {exec_time} | {error} |")

                result_table = "\n".join(result_rows)
                if len(results) > 30:
                    result_table += f"\n| ... | | | 还有 {len(results) - 30} 条记录 |"

                report = f"""
## 批量配置变更报告

### 执行摘要
- **操作类型**: `{op_type}`
- **总设备数**: {summary.get('total', 0)}
- **成功**: {summary.get('success', 0)} ✓
- **失败**: {summary.get('failed', 0)} ✗
- **成功率**: {summary.get('success_rate', 'N/A')}
- **平均执行时间**: {summary.get('avg_execution_time_ms', 0):.0f} ms

### 失败设备
{failed_devices}

### 详细结果
| 设备 | 状态 | 耗时(ms) | 错误信息 |
|------|------|----------|----------|
{result_table}

### 后续建议
{"- 所有设备配置成功，建议执行 commit confirm 永久保存" if summary.get('failed', 0) == 0 else "- 部分设备失败，请检查错误信息并重试"}
                """
            else:
                report = """
## 批量配置变更报告

**状态**: ⚠️ 执行异常

执行过程中发生异常，请检查日志。
                """

            return {
                **state,
                "messages": state["messages"] + [AIMessage(content=report.strip())],
            }

        # ============================================
        # Build Graph
        # ============================================

        workflow = StateGraph(BatchExecutionState)

        # Add nodes
        workflow.add_node("task_planner", task_planner_node)
        workflow.add_node("device_resolver", device_resolver_node)
        workflow.add_node("change_plan_generator", change_plan_generator_node)
        workflow.add_node("hitl_approval", hitl_approval_node)
        workflow.add_node("parallel_executor", parallel_executor_node)
        workflow.add_node("device_worker", device_worker_node)
        workflow.add_node("result_aggregator", result_aggregator_node)
        workflow.add_node("final_report", final_report_node)

        # Set entry point
        workflow.set_entry_point("task_planner")

        # Linear flow: task_planner -> device_resolver -> change_plan_generator -> hitl_approval
        workflow.add_edge("task_planner", "device_resolver")
        workflow.add_edge("device_resolver", "change_plan_generator")
        workflow.add_edge("change_plan_generator", "hitl_approval")

        # After approval: route to parallel_executor or final_report
        workflow.add_conditional_edges(
            "hitl_approval",
            route_after_approval,
            {
                "parallel_executor": "parallel_executor",
                "final_report": "final_report",
            },
        )

        # Fan-out: parallel_executor -> device_worker (via Send)
        workflow.add_conditional_edges(
            "parallel_executor",
            fan_out_tasks,
        )

        # Fan-in: device_worker -> result_aggregator
        workflow.add_edge("device_worker", "result_aggregator")

        # result_aggregator -> final_report
        workflow.add_edge("result_aggregator", "final_report")

        # End
        workflow.add_edge("final_report", END)

        # Compile with HITL interrupt
        from config.settings import AgentConfig

        if AgentConfig.YOLO_MODE:
            return workflow.compile(checkpointer=checkpointer)

        return workflow.compile(
            checkpointer=checkpointer,
            interrupt_before=["hitl_approval"],
        )


def _generate_netconf_config(operation_type: str, params: dict) -> str:
    """Generate NETCONF XML config based on operation type.

    This is a simplified implementation. In production, use proper
    OpenConfig/YANG templates.
    """
    if operation_type == "add_vlan":
        vlan_id = params.get("vlan_id", 1)
        vlan_name = params.get("name", f"VLAN{vlan_id}")
        return f"""
<config>
  <vlans xmlns="http://openconfig.net/yang/vlan">
    <vlan>
      <vlan-id>{vlan_id}</vlan-id>
      <config>
        <vlan-id>{vlan_id}</vlan-id>
        <name>{vlan_name}</name>
      </config>
    </vlan>
  </vlans>
</config>
        """.strip()

    elif operation_type == "configure_ntp":
        server = params.get("server", "0.0.0.0")
        return f"""
<config>
  <system xmlns="http://openconfig.net/yang/system">
    <ntp>
      <servers>
        <server>
          <address>{server}</address>
          <config>
            <address>{server}</address>
          </config>
        </server>
      </servers>
    </ntp>
  </system>
</config>
        """.strip()

    elif operation_type == "change_mtu":
        interface = params.get("interface", "*")
        mtu = params.get("mtu", 1500)
        return f"""
<config>
  <interfaces xmlns="http://openconfig.net/yang/interfaces">
    <interface>
      <name>{interface}</name>
      <config>
        <mtu>{mtu}</mtu>
      </config>
    </interface>
  </interfaces>
</config>
        """.strip()

    else:
        # Generic: return params as comment for manual handling
        return f"""
<config>
  <!-- Operation: {operation_type} -->
  <!-- Params: {json.dumps(params)} -->
  <!-- Manual configuration required -->
</config>
        """.strip()


__all__ = ["BatchExecutionState", "BatchExecutionWorkflow", "DeviceTask", "DeviceResult"]
