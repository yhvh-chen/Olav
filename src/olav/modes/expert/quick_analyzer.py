"""Expert Mode Quick Analyzer - ReAct agent for layer investigation.

The Quick Analyzer:
1. Receives tasks from Supervisor
2. Uses ReAct pattern with SuzieQ tools
3. Executes targeted queries
4. Returns findings to Supervisor

This is the "worker" in the Supervisor-Worker pattern.
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from olav.core.llm import LLMFactory
from olav.modes.expert.supervisor import (
    DiagnosisResult,
    DiagnosisTask,
    LAYER_INFO,
    SUZIEQ_MAX_CONFIDENCE,
)
from olav.modes.shared.debug import DebugContext

logger = logging.getLogger(__name__)


# =============================================================================
# Prompts
# =============================================================================

QUICK_ANALYZER_SYSTEM_PROMPT = """你是网络故障诊断专家 OLAV 的快速分析器，负责调查特定网络层的故障。

## 当前任务
- **层级**: {layer} ({layer_name})
- **描述**: {task_description}
- **建议表**: {suggested_tables}

## 执行策略
1. 使用 SuzieQ 工具查询相关表
2. 分析返回的数据，寻找异常
3. 总结发现，给出置信度评估

## 输出格式
分析完成后，总结以下内容：
- 发现的问题（每个问题一行）
- 置信度评估（0.0-0.6，SuzieQ 历史数据上限）
- 是否需要实时验证（如需 CLI/NETCONF 确认）

## 可用 SuzieQ 表
{available_tables}
"""


# =============================================================================
# Quick Analyzer
# =============================================================================


class QuickAnalyzer:
    """ReAct agent for targeted layer investigation.
    
    Uses SuzieQ tools to query network state and analyze findings.
    
    Usage:
        analyzer = QuickAnalyzer()
        task = DiagnosisTask(
            task_id=1,
            layer="L3",
            description="Check BGP state on R1",
            suggested_tables=["bgp", "routes"],
        )
        result = await analyzer.execute(task)
    """
    
    def __init__(
        self,
        max_iterations: int = 5,
        debug_context: DebugContext | None = None,
    ):
        """Initialize Quick Analyzer.
        
        Args:
            max_iterations: Maximum ReAct iterations per task.
            debug_context: Optional debug context for instrumentation.
        """
        self.max_iterations = max_iterations
        self.debug_context = debug_context
        self.llm = LLMFactory.get_chat_model()
    
    def _get_suzieq_tools(self) -> list[Any]:
        """Get SuzieQ tools for querying.
        
        Returns:
            List of LangChain tools.
        """
        try:
            from olav.tools.suzieq_tool import (
                create_suzieq_query_tool,
                create_suzieq_schema_tool,
            )
            
            return [
                create_suzieq_query_tool(),
                create_suzieq_schema_tool(),
            ]
        except ImportError:
            logger.warning("SuzieQ tools not available, using mock")
            return []
    
    def _get_available_tables_desc(self) -> str:
        """Get description of available SuzieQ tables.
        
        Returns:
            Formatted table descriptions.
        """
        lines = []
        for layer, info in LAYER_INFO.items():
            tables = info["suzieq_tables"]
            if tables:
                lines.append(f"- {layer}: {', '.join(tables)}")
        return "\n".join(lines) if lines else "No tables available"
    
    async def execute(self, task: DiagnosisTask) -> DiagnosisResult:
        """Execute a diagnosis task using ReAct pattern.
        
        Args:
            task: Task from Supervisor.
        
        Returns:
            DiagnosisResult with findings.
        """
        layer_info = LAYER_INFO.get(task.layer, {})
        
        # Build prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", QUICK_ANALYZER_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="messages"),
        ])
        
        # Format system prompt with task details
        formatted_prompt = prompt.partial(
            layer=task.layer,
            layer_name=layer_info.get("name", "Unknown"),
            task_description=task.description,
            suggested_tables=", ".join(task.suggested_tables),
            available_tables=self._get_available_tables_desc(),
        )
        
        # Get tools
        tools = self._get_suzieq_tools()
        
        # If no tools available, return mock result
        if not tools:
            return DiagnosisResult(
                task_id=task.task_id,
                layer=task.layer,
                success=False,
                confidence=0.0,
                findings=["SuzieQ tools not available"],
                error="Tools not configured",
            )
        
        # Create ReAct agent
        try:
            from langchain.agents import AgentExecutor, create_react_agent
            from langchain_core.prompts import PromptTemplate
            
            # Simple ReAct prompt
            react_template = """Answer the following questions as best you can. You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought:{agent_scratchpad}"""
            
            react_prompt = PromptTemplate.from_template(react_template)
            
            agent = create_react_agent(self.llm, tools, react_prompt)
            agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                max_iterations=self.max_iterations,
                verbose=False,
            )
            
            # Execute
            input_msg = f"Investigate {task.layer} ({layer_info.get('name', '')}): {task.description}"
            if task.suggested_filters.get("hostname"):
                input_msg += f"\nDevices to check: {task.suggested_filters['hostname']}"
            
            # Record in debug context
            if self.debug_context:
                self.debug_context.record_tool_call(
                    tool_name="QuickAnalyzer.execute",
                    input_data={"task": task.model_dump()},
                    output_data=None,  # Will be updated after
                    success=True,
                )
            
            result = await agent_executor.ainvoke({"input": input_msg})
            output = result.get("output", "")
            
            # Parse result
            findings = self._parse_findings(output)
            confidence = self._estimate_confidence(findings)
            
            return DiagnosisResult(
                task_id=task.task_id,
                layer=task.layer,
                success=True,
                confidence=confidence,
                findings=findings,
                tool_outputs=[{"raw_output": output}],
            )
        except Exception as e:
            logger.error(f"QuickAnalyzer execution failed: {e}")
            return DiagnosisResult(
                task_id=task.task_id,
                layer=task.layer,
                success=False,
                confidence=0.0,
                findings=[],
                error=str(e),
            )
    
    def _parse_findings(self, output: str) -> list[str]:
        """Parse findings from agent output.
        
        Args:
            output: Raw agent output.
        
        Returns:
            List of finding strings.
        """
        findings = []
        
        # Simple parsing: look for bullet points or numbered items
        lines = output.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Skip metadata lines
            if line.startswith("Thought:") or line.startswith("Action:"):
                continue
            
            # Capture bullet points or significant statements
            if line.startswith("- ") or line.startswith("* "):
                findings.append(line[2:])
            elif any(kw in line.lower() for kw in ["down", "failed", "error", "异常", "故障"]):
                findings.append(line)
        
        return findings[:10]  # Limit to 10 findings
    
    def _estimate_confidence(self, findings: list[str]) -> float:
        """Estimate confidence based on findings.
        
        Args:
            findings: List of finding strings.
        
        Returns:
            Confidence score (0.0 - SUZIEQ_MAX_CONFIDENCE).
        """
        if not findings:
            return 0.0
        
        # More findings = higher confidence (up to SuzieQ cap)
        base_confidence = min(len(findings) * 0.1, 0.4)
        
        # Critical findings boost confidence
        critical_keywords = ["down", "failed", "error", "异常", "故障"]
        critical_count = sum(
            1 for f in findings
            if any(kw in f.lower() for kw in critical_keywords)
        )
        
        critical_boost = min(critical_count * 0.1, 0.2)
        
        return min(base_confidence + critical_boost, SUZIEQ_MAX_CONFIDENCE)
