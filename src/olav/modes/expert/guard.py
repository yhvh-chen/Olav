"""Expert Mode Guard: 两层过滤机制

Layer 1: 相关性过滤 - 判断是否为故障诊断请求
Layer 2: 充分性检查 - 提取并验证诊断必要信息
"""

import logging
from enum import Enum
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class QueryType(str, Enum):
    """用户输入类型分类"""
    FAULT_DIAGNOSIS = "fault_diagnosis"     # 故障诊断 → Expert Mode
    SIMPLE_QUERY = "simple_query"           # 简单查询 → Standard Mode
    CONFIG_CHANGE = "config_change"         # 配置变更 → Standard Mode
    OFF_TOPIC = "off_topic"                 # 非网络话题 → 拒绝


class SymptomType(str, Enum):
    """故障症状类型"""
    CONNECTIVITY = "connectivity"           # 连通性问题 (ping/traceroute)
    PERFORMANCE = "performance"             # 性能问题 (延迟/丢包)
    ROUTING = "routing"                     # 路由问题 (路由缺失/振荡)
    PROTOCOL = "protocol"                   # 协议问题 (BGP down/OSPF邻居)
    HARDWARE = "hardware"                   # 硬件问题 (接口 down/CRC)
    UNKNOWN = "unknown"                     # 无法判断


class DiagnosisContext(BaseModel):
    """诊断上下文 - 从用户输入中提取的结构化信息"""
    symptom: str = Field(description="症状描述，如 '无法访问', 'BGP 邻居 down'")
    symptom_type: SymptomType = Field(default=SymptomType.UNKNOWN, description="症状分类")
    source_device: str | None = Field(default=None, description="发起设备，如 'R3'")
    target_device: str | None = Field(default=None, description="目标设备/IP，如 '10.0.100.100'")
    protocol_hint: str | None = Field(default=None, description="协议提示，如 'BGP', 'OSPF'")
    layer_hint: Literal["L1", "L2", "L3", "L4"] | None = Field(default=None, description="层次提示")


class ExpertModeGuardResult(BaseModel):
    """Expert Mode Guard 输出"""
    query_type: QueryType = Field(description="输入类型分类")
    is_fault_diagnosis: bool = Field(description="是否为故障诊断请求")
    is_sufficient: bool = Field(description="信息是否充分启动诊断")
    missing_info: list[str] = Field(default_factory=list, description="缺失的信息列表")
    clarification_prompt: str | None = Field(default=None, description="追问用户的提示语")
    context: DiagnosisContext | None = Field(default=None, description="提取的诊断上下文")
    redirect_mode: Literal["standard"] | None = Field(default=None, description="重定向目标模式")


class LLMGuardDecision(BaseModel):
    """LLM 输出的结构化决策 - 单次调用完成两层检查"""

    # Layer 1: 相关性判断
    query_type: QueryType = Field(description="用户输入类型分类")
    query_type_reasoning: str = Field(description="分类判断的理由")

    # Layer 2: 信息提取 (仅当 query_type == fault_diagnosis 时有效)
    symptom: str | None = Field(default=None, description="症状描述")
    symptom_type: SymptomType | None = Field(default=None, description="症状类型")
    source_device: str | None = Field(default=None, description="发起设备")
    target_device: str | None = Field(default=None, description="目标设备/IP")
    protocol_hint: str | None = Field(default=None, description="协议提示")
    layer_hint: Literal["L1", "L2", "L3", "L4"] | None = Field(default=None, description="层次提示")

    # 充分性判断
    is_sufficient: bool = Field(default=False, description="信息是否足够启动诊断")
    missing_info: list[str] = Field(default_factory=list, description="缺失的必要信息")
    clarification_prompt: str | None = Field(default=None, description="追问用户的提示")


GUARD_PROMPT_TEMPLATE = """你是网络故障诊断专家。分析用户输入，判断：
1. 这是否是一个故障诊断请求？
2. 如果是，信息是否足够启动诊断？

## 输入类型分类

- fault_diagnosis: 描述网络故障症状，需要诊断根因
  例如: "R3 无法访问 10.0.100.100", "BGP 邻居 down", "接口报错", "路由丢失"

- simple_query: 查询网络状态，无需深度诊断
  例如: "查询 R1 接口", "显示所有 BGP 邻居", "R2 有哪些路由"

- config_change: 配置变更请求
  例如: "配置 OSPF area 0", "修改 BGP neighbor", "添加 ACL"

- off_topic: 非网络相关话题
  例如: "今天天气如何", "写一首诗"

## 症状类型分类

- connectivity: 连通性问题 (无法访问, ping 不通, 丢包)
- performance: 性能问题 (延迟高, 带宽不足)
- routing: 路由问题 (路由缺失, 路由振荡, 次优路径)
- protocol: 协议问题 (BGP down, OSPF 邻居丢失)
- hardware: 硬件问题 (接口 down, CRC 错误)
- unknown: 无法判断

## 充分性要求

故障诊断至少需要：
- symptom: 症状描述 (必须)
- source_device 或 target_device: 至少一个设备/IP (必须)

可选但有助于诊断：
- protocol_hint: 协议类型 (BGP, OSPF, etc.)
- layer_hint: 问题可能的层次 (L1/L2/L3/L4)

## 用户输入

{user_query}

请分析并返回结构化的 JSON 决策。"""


class ExpertModeGuard:
    """Expert Mode 入口过滤器 - 两层过滤机制

    Layer 1: 相关性过滤 (Relevance Filter)
        - fault_diagnosis → 继续到 Layer 2
        - simple_query/config_change → 重定向到 Standard Mode
        - off_topic → 拒绝

    Layer 2: 充分性检查 (Sufficiency Check)
        - 提取诊断上下文 (symptom, devices, protocol)
        - 验证必要信息是否充分
        - 不足时生成追问提示
    """

    def __init__(self, llm: BaseChatModel) -> None:
        """初始化 Guard

        Args:
            llm: LangChain Chat Model 实例
        """
        self.llm = llm.with_structured_output(LLMGuardDecision)
        self.prompt = ChatPromptTemplate.from_template(GUARD_PROMPT_TEMPLATE)

    async def check(self, user_query: str) -> ExpertModeGuardResult:
        """检查用户输入是否适合 Expert Mode

        Args:
            user_query: 用户输入的查询

        Returns:
            ExpertModeGuardResult:
                - is_fault_diagnosis=True, is_sufficient=True → 进入诊断
                - is_fault_diagnosis=True, is_sufficient=False → 追问用户
                - is_fault_diagnosis=False → 重定向到 Standard Mode 或拒绝
        """
        logger.info(f"[ExpertModeGuard] Checking query: {user_query[:50]}...")

        try:
            # 单次 LLM 调用完成两层检查
            messages = self.prompt.format_messages(user_query=user_query)
            decision: LLMGuardDecision = await self.llm.ainvoke(messages)

            logger.info(f"[ExpertModeGuard] Decision: type={decision.query_type}, "
                       f"sufficient={decision.is_sufficient}")

            return self._build_result(decision)

        except Exception as e:
            logger.error(f"[ExpertModeGuard] LLM call failed: {e}")
            # Fail-open: 假设是故障诊断，信息充分
            return ExpertModeGuardResult(
                query_type=QueryType.FAULT_DIAGNOSIS,
                is_fault_diagnosis=True,
                is_sufficient=True,
                context=DiagnosisContext(
                    symptom=user_query,
                    symptom_type=SymptomType.UNKNOWN,
                ),
            )

    def check_sync(self, user_query: str) -> ExpertModeGuardResult:
        """同步版本的 check 方法"""
        import asyncio
        return asyncio.run(self.check(user_query))

    def _build_result(self, decision: LLMGuardDecision) -> ExpertModeGuardResult:
        """根据 LLM 决策构建结果"""

        # 非故障诊断请求 → 重定向或拒绝
        if decision.query_type != QueryType.FAULT_DIAGNOSIS:
            redirect_mode = None
            if decision.query_type in [QueryType.SIMPLE_QUERY, QueryType.CONFIG_CHANGE]:
                redirect_mode = "standard"

            return ExpertModeGuardResult(
                query_type=decision.query_type,
                is_fault_diagnosis=False,
                is_sufficient=False,
                redirect_mode=redirect_mode,
            )

        # 故障诊断请求 → 构建诊断上下文
        context = DiagnosisContext(
            symptom=decision.symptom or "未知故障",
            symptom_type=decision.symptom_type or SymptomType.UNKNOWN,
            source_device=decision.source_device,
            target_device=decision.target_device,
            protocol_hint=decision.protocol_hint,
            layer_hint=decision.layer_hint,
        )

        return ExpertModeGuardResult(
            query_type=QueryType.FAULT_DIAGNOSIS,
            is_fault_diagnosis=True,
            is_sufficient=decision.is_sufficient,
            missing_info=decision.missing_info,
            clarification_prompt=decision.clarification_prompt,
            context=context,
        )

    @staticmethod
    def get_redirect_message(query_type: QueryType) -> str:
        """获取重定向消息"""
        messages = {
            QueryType.SIMPLE_QUERY: "这是一个简单查询请求，将使用标准模式处理。",
            QueryType.CONFIG_CHANGE: "这是一个配置变更请求，将使用标准模式处理。",
            QueryType.OFF_TOPIC: "抱歉，这不是一个网络相关的请求。",
        }
        return messages.get(query_type, "请求类型无法识别。")
