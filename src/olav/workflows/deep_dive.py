"""Deep Dive Workflow - Complex Multi-Step Task Execution.

This workflow handles complex diagnostic and audit tasks that require:
1. Automatic task decomposition (LLM generates Todo List)
2. Recursive diagnostics (max 3 levels deep)
3. Batch parallel execution (30+ devices)
4. Progress tracking with Checkpointer (resume on interruption)

Trigger scenarios:
- Batch audits: "审计所有边界路由器的 BGP 安全配置"
- Cross-domain troubleshooting: "为什么数据中心 A 无法访问数据中心 B？"
- Recursive diagnostics: "深入分析 OSPF 邻居关系异常"

Usage:
    uv run olav.py -e "审计所有边界路由器"
    uv run olav.py --expert "跨域故障深度分析"
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from operator import add
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph

from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager
from olav.workflows.base import BaseWorkflow
from olav.workflows.registry import WorkflowRegistry

# Tools will be called via ToolNode, not directly imported


class TodoItem(TypedDict):
    """Individual task item in the Todo List.

    Extended (Phase 2) with evaluator related fields.
    These optional fields support objective post-execution validation.
    """

    id: int
    task: str
    status: Literal["pending", "in-progress", "completed", "failed"]
    result: str | None
    deps: list[int]  # IDs of prerequisite todos
    # Schema investigation results
    feasibility: Literal["feasible", "uncertain", "infeasible"] | None
    recommended_table: str | None
    schema_notes: str | None
    # External evaluator (Phase 2) - no hardcoded fields needed
    evaluation_passed: bool | None
    evaluation_score: float | None
    failure_reason: str | None


class ExecutionPlan(TypedDict):
    """Execution plan generated from schema investigation."""

    feasible_tasks: list[int]  # Todo IDs that can be executed
    uncertain_tasks: list[int]  # Need user clarification
    infeasible_tasks: list[int]  # Cannot be executed (no schema support)
    recommendations: dict[int, str]  # Todo ID -> recommended approach
    user_approval_required: bool


class DeepDiveState(TypedDict):
    """State for Deep Dive Workflow.

    Fields:
        messages: Conversation history
        todos: List of tasks to execute
        execution_plan: Schema investigation results and execution plan
        current_todo_id: ID of task being executed
        completed_results: Mapping of todo_id -> execution result
        recursion_depth: Current recursion level (0-based)
        max_depth: Maximum allowed recursion depth (default: 3)
        expert_mode: Whether expert mode is enabled
    """

    messages: Annotated[list[BaseMessage], add]
    todos: list[TodoItem]
    execution_plan: ExecutionPlan | None
    current_todo_id: int | None
    completed_results: dict[int, str]
    recursion_depth: int
    max_depth: int
    expert_mode: bool
    # Recursion control flag (Phase 3): set True by recursive_check_node to trigger re-planning
    trigger_recursion: bool | None


@WorkflowRegistry.register(
    name="deep_dive",
    description="Deep Dive 复杂多步任务（任务分解 + 递归诊断 + 批量执行）",
    examples=[
        "审计所有边界路由器的 BGP 配置完整性",
        "批量检查 30+ 设备的接口光功率",
        "从 A 无法访问 B，请排查",
        "为什么业务报障，Web 访问慢？",
        "检查所有核心交换机是否符合安全策略",
        "巡检所有设备的 CPU 和内存使用率",
        "分析跨域连通性问题",
    ],
    triggers=[
        r"审计",
        r"批量",
        r"所有设备",
        r"所有路由器",
        r"多台设备",
        r"为什么",
        r"排查",
        r"诊断问题",
        r"从.*到",
    ],
)
class DeepDiveWorkflow(BaseWorkflow):
    """Deep Dive Workflow for complex multi-step tasks."""

    @property
    def name(self) -> str:
        return "deep_dive"

    @property
    def description(self) -> str:
        return "Deep Dive 复杂多步任务（任务分解 + 递归诊断 + 批量执行）"

    @property
    def tools_required(self) -> list[str]:
        return [
            "suzieq_query",
            "suzieq_schema_search",
            "netconf_tool",
            "cli_tool",
            "search_openconfig_schema",
        ]

    async def validate_input(self, user_query: str) -> tuple[bool, str]:
        """Check if query requires Deep Dive workflow.

        Deep Dive triggers (aligned with Orchestrator classification):
        - Audit tasks ("审计", "audit", "检查完整性")
        - Batch operations ("批量", "所有设备", "所有路由器", "多台设备")
        - Complex diagnostics ("为什么", "诊断问题", "排查故障", "根因分析")
        - Cross-domain troubleshooting ("从 A 到 B", "跨")
        - Recursive diagnostics ("深入分析", "详细排查", "彻底检查")
        """
        import re

        triggers = [
            # 审计类 (Audit)
            r"审计",
            r"audit",
            r"检查.*完整性",
            r"check.*integrity",
            r"配置.*完整",
            # 批量操作 (Batch)
            r"审计所有",
            r"批量",
            r"全部设备",
            r"所有设备",
            r"所有.*路由器",
            r"all.*router",
            r"多.*设备",
            r"multiple.*device",
            r"多台",
            r"\d+台",
            # 复杂诊断
            r"为什么",
            r"why",
            r"诊断.*问题",
            r"diagnose.*issue",
            r"排查.*故障",
            r"troubleshoot",
            r"根因",
            r"root.*cause",
            r"影响范围",
            r"impact.*scope",
            r"为什么.*无法访问",
            r"从.*到.*",
            r"跨",
            r"深入分析",
            r"详细排查",
            r"彻底检查",
            r"递归",
            # 特定协议深度分析
            r"MPLS.*配置",
            r"BGP.*安全",
            r"OSPF.*邻居",
            r"ISIS.*拓扑",
        ]

        for pattern in triggers:
            if re.search(pattern, user_query, re.IGNORECASE):
                return (True, f"Deep Dive trigger detected: '{pattern}'")

        return (False, "Query does not require Deep Dive workflow")

    def __init__(self) -> None:
        self.llm = LLMFactory.get_chat_model(json_mode=False)
        self.llm_json = LLMFactory.get_chat_model(json_mode=True)

        # Tools are imported as functions, not classes
        # Available: suzieq_query, suzieq_schema_search, netconf_get_config

    async def task_planning_node(self, state: DeepDiveState) -> dict:
        """Generate Todo List from user query using LLM.

        Args:
            state: Current workflow state

        Returns:
            Updated state with generated todos
        """
        user_query = state["messages"][-1].content if state["messages"] else ""

        # Load task planning prompt
        prompt = prompt_manager.load_prompt(
            category="workflows/deep_dive",
            name="task_planning",
            user_query=user_query,
            recursion_depth=state.get("recursion_depth", 0),
            max_depth=state.get("max_depth", 3),
        )

        # LLM generates structured Todo List
        messages = [SystemMessage(content=prompt), HumanMessage(content=user_query)]
        response = await self.llm_json.ainvoke(messages)

        # Parse JSON response to TodoItem list
        import json

        try:
            todo_data = json.loads(response.content)
            todos = [
                TodoItem(
                    id=item["id"],
                    task=item["task"],
                    status="pending",
                    result=None,
                    deps=item.get("deps", []),
                )
                for item in todo_data.get("todos", [])
            ]
        except (json.JSONDecodeError, KeyError):
            # Fallback: Create single todo from query
            todos = [TodoItem(id=1, task=user_query, status="pending", result=None, deps=[])]

        return {
            "todos": todos,
            "execution_plan": None,
            "completed_results": {},
            "recursion_depth": state.get("recursion_depth", 0),
            "max_depth": state.get("max_depth", 3),
            "trigger_recursion": False,
        }

    async def schema_investigation_node(self, state: DeepDiveState) -> dict:
        """Investigate schema feasibility for all planned tasks.

        This node:
        1. Calls suzieq_schema_search for each task to discover available tables
        2. Validates keyword mapping against schema results
        3. Categorizes tasks as feasible/uncertain/infeasible
        4. Generates execution plan with recommendations

        Returns:
            Updated state with execution_plan for user approval
        """
        from olav.tools.suzieq_parquet_tool import suzieq_schema_search

        todos = state["todos"]
        feasible_tasks = []
        uncertain_tasks = []
        infeasible_tasks = []
        recommendations = {}

        for todo in todos:
            task_text = todo["task"]
            task_id = todo["id"]

            # Step 1: Keyword-based mapping (heuristic)
            heuristic_mapping = self._map_task_to_table(task_text)

            # Step 2: Schema search (ground truth)
            try:
                schema_result = await suzieq_schema_search.ainvoke({"query": task_text})
                available_tables = schema_result.get("tables", [])

                if not available_tables:
                    # No schema match at all
                    todo["feasibility"] = "infeasible"
                    todo["schema_notes"] = (
                        "❌ SuzieQ schema 未找到相关表。可能需要 NETCONF 直接查询。"
                    )
                    infeasible_tasks.append(task_id)
                    recommendations[task_id] = (
                        "建议使用 NETCONF 查询设备配置，或确认 SuzieQ poller 是否启用相关采集功能。"
                    )

                elif heuristic_mapping:
                    # Validate heuristic against schema
                    heuristic_table = heuristic_mapping[0]
                    if heuristic_table in available_tables:
                        # Perfect match
                        todo["feasibility"] = "feasible"
                        todo["recommended_table"] = heuristic_table
                        todo["schema_notes"] = (
                            f"✅ 表 '{heuristic_table}' 可用，字段: {', '.join(schema_result.get(heuristic_table, {}).get('fields', [])[:5])}"
                        )
                        feasible_tasks.append(task_id)
                        recommendations[task_id] = (
                            f"使用 suzieq_query(table='{heuristic_table}', method='summarize')"
                        )
                    else:
                        # Heuristic mismatch - use first schema suggestion
                        suggested_table = available_tables[0]
                        todo["feasibility"] = "uncertain"
                        todo["recommended_table"] = suggested_table
                        todo["schema_notes"] = (
                            f"⚠️ 关键词映射到 '{heuristic_table}'，但 schema 建议 '{suggested_table}'。"
                            f"可用表: {', '.join(available_tables)}"
                        )
                        uncertain_tasks.append(task_id)
                        recommendations[task_id] = (
                            f"建议确认：任务是否需要 '{suggested_table}' 表？"
                            f"或者使用 '{heuristic_table}' 但可能无相关数据。"
                        )

                else:
                    # No heuristic mapping, but schema has suggestions
                    suggested_table = available_tables[0]
                    todo["feasibility"] = "uncertain"
                    todo["recommended_table"] = suggested_table
                    todo["schema_notes"] = (
                        f"⚠️ 无关键词映射，schema 建议: {', '.join(available_tables[:3])}"
                    )
                    uncertain_tasks.append(task_id)
                    recommendations[task_id] = (
                        f"建议使用 '{suggested_table}' 或由用户指定具体表名。"
                    )

            except Exception as e:
                # Schema search failed
                todo["feasibility"] = "uncertain"
                todo["schema_notes"] = f"⚠️ Schema 调查失败: {e!s}"
                uncertain_tasks.append(task_id)
                recommendations[task_id] = "Schema 查询异常，建议人工确认或重试。"

        # Generate execution plan
        execution_plan: ExecutionPlan = {
            "feasible_tasks": feasible_tasks,
            "uncertain_tasks": uncertain_tasks,
            "infeasible_tasks": infeasible_tasks,
            "recommendations": recommendations,
            "user_approval_required": len(uncertain_tasks) > 0 or len(infeasible_tasks) > 0,
        }

        # Generate plan summary message
        plan_summary = self._format_execution_plan(todos, execution_plan)

        return {
            "todos": todos,
            "execution_plan": execution_plan,
            "messages": [AIMessage(content=plan_summary)],
        }

    def _format_execution_plan(self, todos: list[TodoItem], plan: ExecutionPlan) -> str:
        """Format execution plan for user review."""
        lines = ["## 📋 执行计划（Schema 调研结果）\n"]

        if plan["feasible_tasks"]:
            lines.append(f"### ✅ 可执行任务 ({len(plan['feasible_tasks'])} 个)\n")
            for task_id in plan["feasible_tasks"]:
                todo = next(t for t in todos if t["id"] == task_id)
                lines.append(f"- **任务 {task_id}**: {todo['task']}")
                lines.append(f"  - {todo['schema_notes']}")
                lines.append(f"  - {plan['recommendations'][task_id]}\n")

        if plan["uncertain_tasks"]:
            lines.append(f"### ⚠️ 不确定任务 ({len(plan['uncertain_tasks'])} 个) - 需要确认\n")
            for task_id in plan["uncertain_tasks"]:
                todo = next(t for t in todos if t["id"] == task_id)
                lines.append(f"- **任务 {task_id}**: {todo['task']}")
                lines.append(f"  - {todo['schema_notes']}")
                lines.append(f"  - {plan['recommendations'][task_id]}\n")

        if plan["infeasible_tasks"]:
            lines.append(f"### ❌ 无法执行任务 ({len(plan['infeasible_tasks'])} 个)\n")
            for task_id in plan["infeasible_tasks"]:
                todo = next(t for t in todos if t["id"] == task_id)
                lines.append(f"- **任务 {task_id}**: {todo['task']}")
                lines.append(f"  - {todo['schema_notes']}")
                lines.append(f"  - {plan['recommendations'][task_id]}\n")

        if plan["user_approval_required"]:
            lines.append("\n---\n")
            lines.append(
                "**⏸️ 等待用户审批**: 存在不确定或无法执行的任务，请确认是否继续执行可行任务，或修改计划。\n"
            )
            lines.append("- 输入 `approve` 继续执行可行任务")
            lines.append("- 输入 `modify` 修改任务计划")
            lines.append("- 输入 `abort` 终止执行")

        return "\n".join(lines)

    async def execute_todo_node(self, state: DeepDiveState) -> dict:
        """Execute next eligible todo with real tool invocation where possible.

        Priority:
        1. Heuristic keyword mapping (device, interface, routes, bgp, etc.)
        2. Schema existence check via suzieq_schema_search
        3. Distinguish SCHEMA_NOT_FOUND vs NO_DATA_FOUND vs OK
        4. Fallback to LLM-driven execution prompt if mapping fails or table unsupported
        """
        import asyncio  # Local import to avoid global side-effects

        todos = state["todos"]
        completed_results = state.get("completed_results", {})

        # ------------------------------------------------------------------
        # Parallel batch execution (Phase 3.2)
        # Strategy: Identify all ready & dependency-satisfied todos without deps.
        # Run up to parallel_batch_size concurrently. Falls back to serial path
        # when <=1 independent ready todo.
        # ------------------------------------------------------------------
        parallel_batch_size = state.get("parallel_batch_size", 5)

        ready: list[TodoItem] = []
        for todo in todos:
            if todo["status"] == "pending":
                deps_ok = all(
                    any(t["id"] == dep_id and t["status"] in {"completed", "failed"} for t in todos)
                    for dep_id in todo["deps"]
                )
                if deps_ok:
                    ready.append(todo)

        independent = [t for t in ready if not t["deps"]]

        if len(independent) > 1:
            batch = independent[:parallel_batch_size]
            # Mark batch in-progress
            for t in batch:
                t["status"] = "in-progress"

            async def _execute_single(todo: TodoItem) -> tuple[TodoItem, list[BaseMessage]]:
                task_text = todo["task"].strip()
                mapping = self._map_task_to_table(task_text)
                tool_result: dict | None = None
                messages: list[BaseMessage] = []
                if mapping:
                    table, method, extra_filters = mapping
                    tool_input = {"table": table, "method": method, **extra_filters}
                    try:
                        from olav.tools.suzieq_parquet_tool import (  # type: ignore
                            suzieq_query,
                            suzieq_schema_search,
                        )

                        schema = await suzieq_schema_search.ainvoke({"query": table})
                        available_tables = schema.get("tables", [])
                        if table in available_tables:
                            tool_result = await suzieq_query.ainvoke(tool_input)
                        else:
                            tool_result = {
                                "status": "SCHEMA_NOT_FOUND",
                                "table": table,
                                "message": f"Table '{table}' not present in discovered schema tables.",
                                "available_tables": available_tables,
                            }
                    except Exception as e:
                        tool_result = {
                            "status": "TOOL_ERROR",
                            "error": str(e),
                            "table": table,
                            "method": method,
                            "input": tool_input,
                        }

                if tool_result:
                    classified = self._classify_tool_result(tool_result)
                    # Failure statuses propagate directly
                    if classified["status"] in {
                        "SCHEMA_NOT_FOUND",
                        "NO_DATA_FOUND",
                        "DATA_NOT_RELEVANT",
                        "TOOL_ERROR",
                    }:
                        todo["status"] = "failed"
                        todo["result"] = (
                            f"⚠️ 批量任务失败: {classified['status']} table={classified['table']}"
                        )
                        completed_results[todo["id"]] = todo["result"]
                        return todo, [AIMessage(content=todo["result"])]

                    raw_trunc = str(tool_result.get("data", tool_result))[:400]
                    todo["status"] = "completed"
                    todo["result"] = (
                        f"✅ 并行任务完成 table={classified['table']} count={classified['count']}\n{raw_trunc}"
                    )
                    messages.append(
                        AIMessage(
                            content=f"Parallel task {todo['id']} completed on {classified['table']}"
                        )
                    )
                else:
                    # Fallback LLM path
                    prompt = prompt_manager.load_prompt(
                        category="workflows/deep_dive",
                        name="execute_todo",
                        task=task_text,
                        available_tools="suzieq_query, netconf_tool, search_openconfig_schema",
                    )
                    llm_resp = await self.llm.ainvoke(
                        [
                            SystemMessage(content=prompt),
                            HumanMessage(content=f"Execute task: {task_text}"),
                        ]
                    )
                    todo["status"] = "completed"
                    todo["result"] = llm_resp.content
                    messages.append(
                        AIMessage(content=f"Parallel task {todo['id']} completed via LLM fallback")
                    )

                completed_results[todo["id"]] = todo["result"]
                return todo, messages

            results = await asyncio.gather(
                *[_execute_single(t) for t in batch], return_exceptions=True
            )
            aggregated_messages: list[BaseMessage] = []
            for res in results:
                if isinstance(res, Exception):  # Defensive: unexpected batch error
                    aggregated_messages.append(AIMessage(content=f"批量执行出现未捕获异常: {res}"))
                else:
                    _todo, msgs = res
                    aggregated_messages.extend(msgs)

            # Decide next step message
            aggregated_messages.append(AIMessage(content=f"并行批次完成: {len(batch)} 个任务."))
            return {
                "todos": todos,
                "current_todo_id": batch[-1]["id"],
                "completed_results": completed_results,
                "messages": aggregated_messages,
            }

        # ------------------------------------------------------------------
        # Serial execution fallback (original logic) when 0 or 1 independent
        # ------------------------------------------------------------------
        next_todo: TodoItem | None = None
        for todo in todos:
            if todo["status"] == "pending":
                deps_ok = all(
                    any(t["id"] == dep_id and t["status"] in {"completed", "failed"} for t in todos)
                    for dep_id in todo["deps"]
                )
                if deps_ok or not todo["deps"]:
                    next_todo = todo
                    break

        if not next_todo:
            return {"messages": [AIMessage(content="All pending tasks processed.")]}

        # Mark in-progress
        next_todo["status"] = "in-progress"
        task_text = next_todo["task"].strip()
        tool_result: dict | None = None
        mapping = self._map_task_to_table(task_text)
        tool_messages: list[BaseMessage] = []

        if mapping:
            table, method, extra_filters = mapping
            tool_input = {"table": table, "method": method, **extra_filters}
            try:
                # Local import to avoid global dependency issues
                from olav.tools.suzieq_parquet_tool import (  # type: ignore
                    suzieq_query,
                    suzieq_schema_search,
                )

                # Discover available tables; suzieq_schema_search returns {"tables": [...], "bgp": {...}, ...}
                schema = await suzieq_schema_search.ainvoke({"query": table})
                available_tables = schema.get("tables", [])

                if table in available_tables:
                    tool_result = await suzieq_query.ainvoke(tool_input)

                    # 方案2: 字段语义验证 - 检查返回字段是否与任务相关
                    if (
                        tool_result
                        and "columns" in tool_result
                        and tool_result.get("status") != "NO_DATA_FOUND"
                    ):
                        is_relevant = self._validate_field_relevance(
                            task_text=task_text,
                            returned_columns=tool_result["columns"],
                            queried_table=table,
                        )
                        if not is_relevant:
                            # Data returned but not relevant to task
                            tool_result = {
                                "status": "DATA_NOT_RELEVANT",
                                "table": table,
                                "returned_columns": tool_result["columns"],
                                "message": f"表 '{table}' 返回了数据，但字段与任务需求不匹配。",
                                "hint": f"任务关键词: {self._extract_task_keywords(task_text)}，返回字段: {tool_result['columns'][:5]}",
                                "suggestion": "可能需要使用 NETCONF 查询或重新规划任务。",
                            }
                else:
                    tool_result = {
                        "status": "SCHEMA_NOT_FOUND",
                        "table": table,
                        "message": f"Table '{table}' not present in discovered schema tables.",
                        "hint": "Use suzieq_schema_search with a broader query or verify poller collection.",
                        "available_tables": available_tables,
                    }
            except Exception as e:
                tool_result = {
                    "status": "TOOL_ERROR",
                    "error": str(e),
                    "table": table,
                    "method": method,
                    "input": tool_input,
                }

        if tool_result:
            classified = self._classify_tool_result(tool_result)
            summary = (
                f"TOOL_CALL table={classified['table']} status={classified['status']} "
                f"count={classified['count']}"
            )

            # CRITICAL: 防止 LLM 幻觉 - 在遇到错误状态时直接返回失败，不继续处理
            if classified["status"] in {
                "SCHEMA_NOT_FOUND",
                "NO_DATA_FOUND",
                "DATA_NOT_RELEVANT",
                "TOOL_ERROR",
            }:
                error_msg = (
                    f"⚠️ 任务执行失败: {classified['status']}\n"
                    f"表: {classified['table']}\n"
                    f"原因: {tool_result.get('message') or tool_result.get('error', '未知错误')}\n"
                    f"提示: {tool_result.get('hint', 'N/A')}\n"
                )

                # DATA_NOT_RELEVANT 需要额外说明
                if classified["status"] == "DATA_NOT_RELEVANT":
                    error_msg += (
                        f"\n⚠️ **数据语义不匹配**: 查询的表返回了数据，但字段与任务需求不相关。\n"
                        f"建议: {tool_result.get('suggestion', '重新规划任务或使用 NETCONF 直接查询')}\n"
                    )

                error_msg += (
                    "\n⛔ **严格禁止编造数据** - 无相关数据即报告失败，不推测或生成虚假结果。"
                )

                next_todo["status"] = "failed"
                next_todo["result"] = error_msg
                completed_results[next_todo["id"]] = error_msg

                return {
                    "todos": todos,
                    "current_todo_id": next_todo["id"],
                    "completed_results": completed_results,
                    "messages": [AIMessage(content=error_msg)],
                }

            # 成功状态：格式化结果
            raw_trunc = str(tool_result.get("data", tool_result))[:800]
            result_text = f"{summary}\n\n✅ 数据摘要:\n{raw_trunc}"
            tool_messages.append(
                AIMessage(
                    content=f"Used suzieq_query on {classified['table']} status={classified['status']} count={classified['count']}"
                )
            )
        else:
            # Fallback to LLM execution strategy
            prompt = prompt_manager.load_prompt(
                category="workflows/deep_dive",
                name="execute_todo",
                task=task_text,
                available_tools="suzieq_query, netconf_tool, search_openconfig_schema",
            )
            messages = [
                SystemMessage(content=prompt),
                HumanMessage(content=f"Execute task: {task_text}"),
            ]
            llm_resp = await self.llm.ainvoke(messages)
            result_text = llm_resp.content

        # Complete todo (only if not already marked failed above)
        if next_todo["status"] != "failed":
            next_todo["status"] = "completed"
        next_todo["result"] = result_text

        # ------------------------------------------------------------------
        # Phase 2: External Evaluator integration (Schema-Aware dynamic)
        # ------------------------------------------------------------------
        try:
            if next_todo["status"] == "completed" and tool_result:
                from olav.evaluators.config_compliance import ConfigComplianceEvaluator

                evaluator = ConfigComplianceEvaluator()
                eval_result = await evaluator.evaluate(next_todo, tool_result)

                next_todo["evaluation_passed"] = eval_result.passed
                next_todo["evaluation_score"] = eval_result.score

                if not eval_result.passed:
                    next_todo["failure_reason"] = eval_result.feedback
                    # Reclassify status to failed and append evaluator feedback
                    next_todo["status"] = "failed"
                    appended = f"\n🔍 评估未通过: {eval_result.feedback}"
                    next_todo["result"] = (next_todo["result"] or "") + appended
        except Exception as eval_err:
            # Non-fatal – store failure_reason for visibility
            next_todo["evaluation_passed"] = False
            next_todo["evaluation_score"] = 0.0
            next_todo["failure_reason"] = f"Evaluator error: {eval_err}"

        completed_results[next_todo["id"]] = next_todo["result"]

        completion = AIMessage(content=f"Completed task {next_todo['id']}: {result_text[:600]}")
        return {
            "todos": todos,
            "current_todo_id": next_todo["id"],
            "completed_results": completed_results,
            "messages": [*tool_messages, completion],
        }

    def _map_task_to_table(self, task: str) -> tuple[str, str, dict] | None:
        """Map natural language task to (table, method, filters) using ordered specificity.

        Order matters: more specific/general inventory tasks first, then protocol.
        Returns None if no mapping found (will trigger schema investigation).
        """
        lower = task.lower()

        candidates: list[tuple[list[str], str, str]] = [
            # Inventory / device list
            (["设备列表", "所有设备", "审计设备", "device", "设备"], "device", "summarize"),
            # Interfaces
            (["接口", "端口", "interface", "物理", "rx", "tx", "链路"], "interfaces", "summarize"),
            # Routing / prefixes
            (["路由", "前缀", "routes", "lpm"], "routes", "summarize"),
            # OSPF
            (["ospf"], "ospfIf", "summarize"),
            # LLDP
            (["lldp"], "lldp", "summarize"),
            # MAC
            (["mac", "二层"], "macs", "summarize"),
            # BGP (put later to avoid greedy matching of '边界')
            (["bgp", "peer", "邻居", "边界"], "bgp", "summarize"),
        ]
        for keywords, table, method in candidates:
            if any(k in lower for k in keywords):
                import re

                hosts = re.findall(r"\b([A-Za-z]{1,4}\d{1,2})\b", task)
                filters: dict[str, Any] = {}
                if hosts:
                    filters["hostname"] = hosts[0]
                return table, method, filters
        return None

    def _classify_tool_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Normalize tool result into status/count/table for summary lines."""
        status = "OK"
        table = result.get("table", "unknown")
        count = result.get("count")
        if count is None and isinstance(result.get("data"), list):
            count = len(result.get("data", []))

        # Priority 1: Explicit DATA_NOT_RELEVANT status (field validation failed)
        if result.get("status") == "DATA_NOT_RELEVANT":
            status = "DATA_NOT_RELEVANT"
        # Priority 2: Explicit error field (tool execution failed)
        elif "error" in result:
            error_msg = str(result["error"])
            # Check if error indicates unknown table (schema validation)
            if "Unknown table" in error_msg or "available_tables" in result:
                status = "SCHEMA_NOT_FOUND"
            else:
                status = "TOOL_ERROR"
        # Priority 3: Explicit schema not found status (from our validation)
        elif result.get("status") == "SCHEMA_NOT_FOUND":
            status = "SCHEMA_NOT_FOUND"
        # Priority 4: NO_DATA_FOUND sentinel in first data record
        elif isinstance(result.get("data"), list) and result["data"]:
            first = result["data"][0]
            if isinstance(first, dict) and first.get("status") == "NO_DATA_FOUND":
                status = "NO_DATA_FOUND"
        # Priority 5: Empty data list
        elif isinstance(result.get("data"), list) and len(result.get("data", [])) == 0:
            status = "NO_DATA_FOUND"

        return {"status": status, "table": table, "count": count if count is not None else 0}

    def _validate_field_relevance(
        self, task_text: str, returned_columns: list[str], queried_table: str
    ) -> bool:
        """Validate if returned columns are semantically relevant to task (方案2).

        Args:
            task_text: Original task description
            returned_columns: Field names returned from query
            queried_table: Table that was queried

        Returns:
            True if fields appear relevant, False otherwise
        """
        # Extract task keywords (nouns/technical terms)
        task_keywords = self._extract_task_keywords(task_text)
        columns_str = " ".join(returned_columns).lower()

        # Check if任何任务关键词出现在字段名中
        # 例如: task="MPLS配置" keywords=["mpls"], columns=["hostname", "model"] → False
        #       task="BGP状态" keywords=["bgp"], columns=["peer", "asn", "state"] → True
        matches = sum(1 for kw in task_keywords if kw in columns_str)

        # Threshold: at least 1 keyword match, or it's a generic device/interface query
        if matches > 0:
            return True

        # Special case: device/interfaces are generic inventory, acceptable for most tasks
        if queried_table in {"device", "interfaces"}:
            return True

        # No semantic match
        return False

    def _extract_task_keywords(self, task_text: str) -> list[str]:
        """Extract technical keywords from task description."""
        lower = task_text.lower()
        # Common network protocol/feature keywords
        keywords = [
            "mpls",
            "ldp",
            "rsvp",
            "bgp",
            "ospf",
            "eigrp",
            "isis",
            "vlan",
            "vxlan",
            "evpn",
            "interface",
            "route",
            "prefix",
            "neighbor",
            "peer",
            "session",
            "tunnel",
            "policy",
            "qos",
            "acl",
            "nat",
            "firewall",
            "vpn",
        ]
        return [kw for kw in keywords if kw in lower]

    async def should_continue(
        self, state: DeepDiveState
    ) -> Literal["execute_todo", "recursive_check"]:
        """Decide whether to continue executing todos or move to recursive check.

        Args:
            state: Current workflow state

        Returns:
            Next node to execute
        """
        todos = state["todos"]
        pending_count = sum(1 for t in todos if t["status"] == "pending")

        if pending_count > 0:
            return "execute_todo"
        return "recursive_check"

    async def recursive_check_node(self, state: DeepDiveState) -> dict:
        """Check if recursive deep dive is needed.

        Phase 3.4 Enhancement: Handles multiple failures in parallel, not just the first one.
        Creates focused sub-tasks for each failed todo (up to max_failures_per_recursion).

        Args:
            state: Current workflow state

        Returns:
            Updated state with potential new sub-todos for all failures
        """
        recursion_depth = state.get("recursion_depth", 0)
        max_depth = state.get("max_depth", 3)
        max_failures_per_recursion = (
            3  # Limit parallel failure investigation to avoid prompt explosion
        )

        # Depth guard
        if recursion_depth >= max_depth:
            return {
                "messages": [
                    AIMessage(
                        content=f"Max recursion depth ({max_depth}) reached. Moving to summary."
                    )
                ],
                "trigger_recursion": False,
            }

        todos = state.get("todos", [])
        failed_todos = [t for t in todos if t.get("status") == "failed"]

        if not failed_todos:
            return {
                "messages": [AIMessage(content="No deeper analysis needed.")],
                "trigger_recursion": False,
            }

        # PHASE 3.4: Handle multiple failures (not just first one)
        # Limit to top N failures to avoid overwhelming prompt/planning
        failures_to_analyze = failed_todos[:max_failures_per_recursion]

        # Build recursive prompt for ALL selected failures
        failure_summaries = []
        for failed in failures_to_analyze:
            parent_task_id = failed["id"]
            parent_task_text = failed["task"]
            parent_result = (failed.get("result") or "")[
                :400
            ]  # Truncate per failure to fit multiple
            parent_reason = failed.get("failure_reason", "Unknown")

            failure_summaries.append(
                f"  • 失败任务 {parent_task_id}: {parent_task_text}\n"
                f"    失败原因: {parent_reason}\n"
                f"    输出摘要: {parent_result}\n"
            )

        recursive_prompt = (
            f"递归深入分析: 检测到 {len(failures_to_analyze)} 个失败任务，需要生成更细粒度的子任务。\n\n"
            "失败任务列表:\n" + "\n".join(failure_summaries) + "\n\n"
            "请遵循要求: \n"
            f"1) 为每个失败任务生成 1-2 个更具体的子任务（总共 {len(failures_to_analyze) * 2} 个左右）。\n"
            "2) 子任务需更具体，例如聚焦某协议实例、邻居、接口或字段。\n"
            "3) 避免与父任务完全重复。\n"
            '4) 使用 JSON 输出: {\n  "todos": [ {"id": <int>, "task": <str>, "deps": [] } ]\n}。\n'
            "5) ID 从现有最大 ID + 1 开始递增。\n"
            "6) 在 task 文本中包含父任务引用: '(parent:<id>)'，例如 '检查 R1 BGP 配置 (parent:3)'。\n"
            "7) 如果某失败任务无法进一步细化，生成一个验证性任务，例如 '验证采集是否缺失 (parent:<id>)'。\n"
        )

        return {
            "messages": [HumanMessage(content=recursive_prompt)],
            "recursion_depth": recursion_depth + 1,
            "trigger_recursion": True,
        }

    async def should_recurse(
        self, state: DeepDiveState
    ) -> Literal["final_summary", "task_planning"]:
        """Decide whether to recurse or finalize.

        Args:
            state: Current workflow state

        Returns:
            Next node to execute
        """
        if state.get("trigger_recursion"):
            return "task_planning"
        return "final_summary"

    async def final_summary_node(self, state: DeepDiveState) -> dict:
        """Generate final summary report from all completed todos.

        Args:
            state: Current workflow state

        Returns:
            Updated state with final summary message
        """
        todos = state["todos"]
        completed_results = state.get("completed_results", {})

        # Load summary prompt
        prompt = prompt_manager.load_prompt(
            category="workflows/deep_dive",
            name="final_summary",
            todos=str(todos),
            results=str(completed_results),
        )

        messages = [SystemMessage(content=prompt)]
        response = await self.llm.ainvoke(messages)

        return {
            "messages": [AIMessage(content=response.content)],
        }

    def build_graph(self, checkpointer: AsyncPostgresSaver) -> StateGraph:
        """Build Deep Dive Workflow graph with schema investigation and HITL approval.

        Flow:
        1. task_planning → Generate todos
        2. schema_investigation → Validate feasibility, generate execution plan
        3. [INTERRUPT] → Wait for user approval/modification
        4. execute_todo → Execute approved tasks
        5. recursive_check → Determine if deeper analysis needed
        6. final_summary → Generate report

        Args:
            checkpointer: PostgreSQL checkpointer for state persistence

        Returns:
            Compiled StateGraph with HITL interrupts
        """
        workflow = StateGraph(DeepDiveState)

        # Add nodes
        workflow.add_node("task_planning", self.task_planning_node)
        workflow.add_node("schema_investigation", self.schema_investigation_node)
        workflow.add_node("execute_todo", self.execute_todo_node)
        workflow.add_node("recursive_check", self.recursive_check_node)
        workflow.add_node("final_summary", self.final_summary_node)

        # Define edges
        workflow.set_entry_point("task_planning")
        workflow.add_edge("task_planning", "schema_investigation")

        # HITL approval after schema investigation
        # LangGraph will interrupt here if execution_plan.user_approval_required = True
        workflow.add_edge("schema_investigation", "execute_todo")

        workflow.add_conditional_edges(
            "execute_todo",
            self.should_continue,
            {
                "execute_todo": "execute_todo",  # Loop back for next todo
                "recursive_check": "recursive_check",
            },
        )
        workflow.add_conditional_edges(
            "recursive_check",
            self.should_recurse,
            {
                "task_planning": "task_planning",  # Recurse
                "final_summary": "final_summary",
            },
        )
        workflow.add_edge("final_summary", END)

        # Compile with checkpointer and interrupt points
        # When execution_plan.user_approval_required = True, graph will pause
        return workflow.compile(
            checkpointer=checkpointer,
            interrupt_before=["execute_todo"],  # Always pause before execution for review
        )
