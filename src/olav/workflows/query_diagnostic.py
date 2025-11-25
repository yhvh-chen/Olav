"""Query and Diagnostic Workflow.

Scope:
- Network state queries (interfaces, BGP, OSPF, routes, etc.)
- Root cause analysis (why BGP down, why interface flapping, etc.)
- Historical trend analysis

Tool Chain:
- SuzieQ (macro analysis via Parquet)
- OpenSearch (schema/memory search)
- NETCONF/CLI (micro diagnosis, read-only)

Workflow:
    User Query
    ↓
    [Macro Analysis] → SuzieQ historical data
    ↓
    [Self Evaluation] → Sufficient data?
    ├─ Yes → [Final Answer]
    └─ No → [Micro Diagnosis] → NETCONF/CLI get-config
                ↓
            [Final Answer]
"""

import sys

if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from typing import Literal

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager
from olav.tools.nornir_tool import cli_tool, netconf_tool
from olav.tools.opensearch_tool import search_openconfig_schema
from olav.tools.suzieq_parquet_tool import suzieq_query, suzieq_schema_search

from .base import BaseWorkflow, BaseWorkflowState
from .registry import WorkflowRegistry


class QueryDiagnosticState(BaseWorkflowState):
    """State for query/diagnostic workflow."""

    macro_data: dict | None  # SuzieQ 分析结果
    micro_data: dict | None  # NETCONF 诊断结果
    needs_micro: bool  # 是否需要微观诊断


@WorkflowRegistry.register(
    name="query_diagnostic",
    description="网络状态查询与故障诊断（SuzieQ 宏观 → NETCONF 微观）",
    examples=[
        "查询 R1 的 BGP 邻居状态",
        "Switch-A 的接口 Gi0/1 状态如何？",
        "检查所有核心路由器的 CPU 使用率",
        "为什么 OSPF 邻居不起来？",
        "BGP session 为什么 down？",
        "查看设备 R2 的路由表",
        "接口带宽利用率是多少？",
    ],
    triggers=[r"BGP", r"OSPF", r"接口.*状态", r"路由.*表", r"CPU", r"内存", r"邻居"],
)
class QueryDiagnosticWorkflow(BaseWorkflow):
    """Query and diagnostic workflow implementation."""

    @property
    def name(self) -> str:
        return "query_diagnostic"

    @property
    def description(self) -> str:
        return "网络状态查询与故障诊断（SuzieQ 宏观 → NETCONF 微观）"

    @property
    def tools_required(self) -> list[str]:
        return [
            "suzieq_query",
            "suzieq_schema_search",
            "search_episodic_memory",
            "search_openconfig_schema",
            "netconf_tool",  # Read-only get-config
            "cli_tool",  # Fallback read-only
        ]

    async def validate_input(self, user_query: str) -> tuple[bool, str]:
        """Check if query is about network state or diagnostics."""
        query_lower = user_query.lower()

        # 排除配置变更关键词（更全面）
        config_keywords = [
            "修改",
            "配置",
            "设置",
            "添加",
            "删除",
            "shutdown",
            "no shutdown",
            "change",
            "modify",
            "set",
            "add",
            "delete",
            "configure",
            "config",
            "edit",
            "commit",
            "rollback",
            "create",
            "remove",
        ]
        if any(kw in query_lower for kw in config_keywords):
            return False, "配置变更请求，应使用 device_execution workflow"

        # 排除 NetBox 管理关键词
        netbox_keywords = [
            "设备清单",
            "添加设备",
            "ip分配",
            "ip地址",
            "站点",
            "机架",
            "电缆",
            "inventory",
            "device list",
            "add device",
            "ip assignment",
            "site",
            "rack",
            "cable",
            "netbox",
        ]
        if any(kw in query_lower for kw in netbox_keywords):
            return False, "NetBox 管理请求，应使用 netbox_management workflow"

        # 匹配查询/诊断关键词
        query_keywords = [
            "查询",
            "显示",
            "状态",
            "为什么",
            "原因",
            "诊断",
            "排查",
            "分析",
            "show",
            "query",
            "why",
            "cause",
            "diagnose",
            "analyze",
            "check",
            "bgp",
            "ospf",
            "route",
            "interface",
            "接口",
            "路由",
        ]
        if any(kw in query_lower for kw in query_keywords):
            return True, "匹配查询/诊断场景"

        # 默认接受（宽松策略）
        return True, "默认分类为查询任务"

    def build_graph(self, checkpointer: BaseCheckpointSaver) -> StateGraph:
        """Build query/diagnostic workflow graph."""

        # Define tool nodes
        macro_tools = [suzieq_query, suzieq_schema_search]
        macro_tools_node = ToolNode(macro_tools)

        micro_tools = [search_openconfig_schema, netconf_tool, cli_tool]
        micro_tools_node = ToolNode(micro_tools)

        async def macro_analysis_node(state: QueryDiagnosticState) -> QueryDiagnosticState:
            """Macro analysis using SuzieQ historical data."""
            llm = LLMFactory.get_chat_model()
            llm_with_tools = llm.bind_tools(macro_tools)

            # Use the initial user query for prompt context
            user_query = state["messages"][0].content
            macro_prompt = prompt_manager.load_prompt(
                "workflows/query_diagnostic", "macro_analysis", user_query=user_query
            )

            response = await llm_with_tools.ainvoke(
                [SystemMessage(content=macro_prompt), *state["messages"]]
            )

            return {
                **state,
                "messages": state["messages"] + [response],
                "iteration_count": state.get("iteration_count", 0) + 1,
            }

        async def self_evaluation_node(state: QueryDiagnosticState) -> QueryDiagnosticState:
            """Evaluate if macro data is sufficient for answer."""
            llm = LLMFactory.get_chat_model()

            # Extract macro analysis result from the last message
            macro_result = state["messages"][-1].content
            macro_data = {"analysis": macro_result}

            eval_prompt = f"""评估当前宏观分析数据是否足以回答用户问题。

用户请求: {state["messages"][0].content}
宏观分析: {macro_result}

评估标准：
- 如果用户询问"为什么"/"原因"，仅历史数据不足，需要实时配置验证 → needs_micro=True
- 如果发现异常状态（NotEstd/down/异常），需要获取实时配置确认根因 → needs_micro=True
- 如果只是统计/概览/列表，历史数据已足够 → needs_micro=False

返回 true 或 false
"""

            await llm.ainvoke([SystemMessage(content=eval_prompt)])

            # 解析响应（简化版：基于触发词）
            user_query = state["messages"][0].content.lower()
            trigger_words = ["为什么", "原因", "诊断", "排查", "why", "cause", "down", "failed"]
            needs_micro = any(word in user_query for word in trigger_words)

            return {
                **state,
                "macro_data": macro_data,
                "needs_micro": needs_micro,
                "iteration_count": state.get("iteration_count", 0) + 1,
            }

        async def micro_diagnosis_node(state: QueryDiagnosticState) -> QueryDiagnosticState:
            """Micro diagnosis using NETCONF/CLI (read-only)."""
            llm = LLMFactory.get_chat_model()
            llm_with_tools = llm.bind_tools(micro_tools)

            user_query = state["messages"][0].content
            macro_data = state.get("macro_data", {})
            micro_prompt = prompt_manager.load_prompt(
                "workflows/query_diagnostic",
                "micro_diagnosis",
                user_query=user_query,
                macro_data=str(macro_data),
            )

            response = await llm_with_tools.ainvoke(
                [SystemMessage(content=micro_prompt), *state["messages"]]
            )

            return {
                **state,
                "messages": state["messages"] + [response],
                "iteration_count": state.get("iteration_count", 0) + 1,
            }

        async def final_answer_node(state: QueryDiagnosticState) -> QueryDiagnosticState:
            """Generate final answer combining all analysis."""
            llm = LLMFactory.get_chat_model()

            # Extract micro diagnosis result if available
            micro_result = state["messages"][-1].content if state.get("needs_micro") else None
            micro_data = {"diagnosis": micro_result} if micro_result else None

            final_prompt = f"""综合所有分析，给出最终答案。

用户请求: {state["messages"][0].content}
宏观分析: {state.get("macro_data")}
微观诊断: {micro_data}

要求：
- 直接回答用户问题
- 如果是诊断任务，给出明确根因
- 使用清晰的结构化输出（表格/列表）
"""

            response = await llm.ainvoke([SystemMessage(content=final_prompt)])

            return {
                **state,
                "micro_data": micro_data,
                "messages": state["messages"] + [AIMessage(content=response.content)],
            }

        def route_after_evaluation(
            state: QueryDiagnosticState,
        ) -> Literal["micro_diagnosis", "final_answer"]:
            """Route based on evaluation result."""
            if state.get("needs_micro", False):
                return "micro_diagnosis"
            return "final_answer"

        # Build graph
        workflow = StateGraph(QueryDiagnosticState)

        workflow.add_node("macro_analysis", macro_analysis_node)
        workflow.add_node("macro_tools", macro_tools_node)
        workflow.add_node("self_evaluation", self_evaluation_node)
        workflow.add_node("micro_diagnosis", micro_diagnosis_node)
        workflow.add_node("micro_tools", micro_tools_node)
        workflow.add_node("final_answer", final_answer_node)

        workflow.set_entry_point("macro_analysis")

        # Macro Analysis Loop
        workflow.add_conditional_edges(
            "macro_analysis",
            tools_condition,
            {"tools": "macro_tools", "__end__": "self_evaluation"},
        )
        workflow.add_edge("macro_tools", "macro_analysis")

        # Evaluation Routing
        workflow.add_conditional_edges(
            "self_evaluation",
            route_after_evaluation,
            {
                "micro_diagnosis": "micro_diagnosis",
                "final_answer": "final_answer",
            },
        )

        # Micro Diagnosis Loop
        workflow.add_conditional_edges(
            "micro_diagnosis", tools_condition, {"tools": "micro_tools", "__end__": "final_answer"}
        )
        workflow.add_edge("micro_tools", "micro_diagnosis")

        workflow.add_edge("final_answer", END)

        return workflow.compile(checkpointer=checkpointer)


__all__ = ["QueryDiagnosticState", "QueryDiagnosticWorkflow"]
