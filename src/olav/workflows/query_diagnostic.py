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

import logging
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
from olav.middleware.tool_middleware import tool_middleware
from olav.tools.document_tool import search_documents, search_rfc, search_vendor_docs
from olav.tools.netbox_tool import netbox_api_call, netbox_schema_search
from olav.tools.nornir_tool import cli_tool, netconf_tool
from olav.tools.opensearch_tool import (
    search_episodic_memory,
    search_openconfig_schema,
)
from olav.tools.suzieq_parquet_tool import suzieq_query, suzieq_schema_search
from olav.tools.syslog_tool import syslog_search

from .base import BaseWorkflow, BaseWorkflowState
from .registry import WorkflowRegistry

logger = logging.getLogger(__name__)


class QueryDiagnosticState(BaseWorkflowState):
    """State for query/diagnostic workflow."""

    macro_data: dict | None  # SuzieQ 分析结果
    micro_data: dict | None  # NETCONF 诊断结果
    needs_micro: bool  # 是否需要微观诊断


@WorkflowRegistry.register(
    name="query_diagnostic",
    description="网络状态查询与故障诊断（SuzieQ 宏观 → NETCONF 微观），以及知识检索",
    examples=[
        "查询 R1 的 BGP 邻居状态",
        "Switch-A 的接口 Gi0/1 状态如何？",
        "检查所有核心路由器的 CPU 使用率",
        "为什么 OSPF 邻居不起来？",
        "BGP session 为什么 down？",
        "查看设备 R2 的路由表",
        "接口带宽利用率是多少？",
        # Document RAG examples
        "搜索 Cisco 配置指南",
        "查找关于 BGP 路由策略的文档",
        "搜索 RFC 7911 关于 ADD-PATH 的内容",
    ],
    triggers=[
        r"BGP",
        r"OSPF",
        r"接口.*状态",
        r"路由.*表",
        r"CPU",
        r"内存",
        r"邻居",
        # Document triggers
        r"文档",
        r"document",
        r"知识库",
        r"搜索.*文档",
        r"RFC",
    ],
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
            # Layer 1: Knowledge Base
            "search_episodic_memory",
            "search_openconfig_schema",
            # Layer 2: Cached Telemetry
            "suzieq_query",
            "suzieq_schema_search",
            # Layer 3: Source of Truth
            "netbox_api_call",
            "netbox_schema_search",
            "syslog_search",
            # Layer 4: Live Device (read-only)
            "netconf_tool",
            "cli_tool",
            # Document RAG tools
            "search_documents",
            "search_vendor_docs",
            "search_rfc",
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
            return False, "Config change request, should use device_execution workflow"

        # Exclude NetBox management keywords
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
            return False, "NetBox management request, should use netbox_management workflow"

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
        # Macro tools: SuzieQ + Knowledge Base for historical data analysis
        macro_tools = [
            # Layer 1: Knowledge Base
            search_episodic_memory,
            search_openconfig_schema,
            # Layer 2: Cached Telemetry
            suzieq_query,
            suzieq_schema_search,
        ]
        macro_tools_node = ToolNode(macro_tools)

        # Micro tools: Real-time device data + Source of Truth + Documents
        micro_tools = [
            # Layer 3: Source of Truth
            netbox_api_call,
            netbox_schema_search,
            syslog_search,
            # Layer 4: Live Device (read-only)
            netconf_tool,
            cli_tool,
            # Document RAG tools
            search_documents,
            search_vendor_docs,
            search_rfc,
        ]
        micro_tools_node = ToolNode(micro_tools)

        async def macro_analysis_node(state: QueryDiagnosticState) -> QueryDiagnosticState:
            """Macro analysis using SuzieQ historical data.

            Uses ToolMiddleware to automatically inject tool descriptions.
            """
            llm = LLMFactory.get_chat_model()
            llm_with_tools = llm.bind_tools(macro_tools)

            # Use the initial user query for prompt context
            user_query = state["messages"][0].content

            # Load simplified base prompt
            base_prompt = prompt_manager.load_prompt(
                "workflows/query_diagnostic", "macro_analysis", user_query=user_query
            )

            # Use ToolMiddleware to enrich prompt with tool descriptions
            enriched_prompt = tool_middleware.enrich_prompt(
                base_prompt=base_prompt,
                tools=macro_tools,
                include_guides=True,  # Include capability guides for SuzieQ
            )

            response = await llm_with_tools.ainvoke(
                [SystemMessage(content=enriched_prompt), *state["messages"]]
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

            eval_prompt = f"""Evaluate whether the current macro analysis data is sufficient to answer the user's question.

User request: {state["messages"][0].content}
Macro analysis: {macro_result}

Evaluation criteria:
- If user asks "why"/"reason", historical data alone is insufficient, needs real-time config verification → needs_micro=True
- If anomalous state detected (NotEstd/down/error), need real-time config to confirm root cause → needs_micro=True
- If just statistics/overview/list, historical data is sufficient → needs_micro=False

Return true or false
"""

            await llm.ainvoke([SystemMessage(content=eval_prompt)])

            # Parse response (simplified: based on trigger words)
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

            # Load simplified prompt and enrich with ToolMiddleware
            micro_prompt = prompt_manager.load_prompt(
                "workflows/query_diagnostic",
                "micro_diagnosis",
                user_query=user_query,
                macro_analysis_result=str(macro_data),
            )

            # Use module-level tool_middleware singleton
            enriched_prompt = tool_middleware.enrich_prompt(
                base_prompt=micro_prompt,
                tools=micro_tools,
                include_guides=True,  # Include capability guides for diagnosis
            )

            response = await llm_with_tools.ainvoke(
                [SystemMessage(content=enriched_prompt), *state["messages"]]
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

            final_prompt = f"""Synthesize all analysis and provide final answer.

User request: {state["messages"][0].content}
Macro analysis: {state.get("macro_data")}
Micro diagnosis: {micro_data}

Requirements:
- Answer user's question directly
- If diagnostic task, provide clear root cause
- Use clear structured output (tables/lists)
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
