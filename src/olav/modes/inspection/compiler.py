"""Intent Compiler - LLM-driven intent to query plan compilation.

This module implements the IntentCompiler that translates natural language
inspection intents into structured SuzieQ query plans.

Key Features:
- LLM-driven intent compilation with structured output
- Schema-aware: uses suzieq-schema index for context
- Caching: avoids redundant LLM calls for same intents
- Fallback: graceful degradation when LLM fails

Example:
    compiler = IntentCompiler()

    # Compile intent to query plan
    plan = await compiler.compile(
        intent="检查 BGP 邻居状态是否 Established",
        severity="critical"
    )

    # Result:
    # QueryPlan(
    #     table="bgp",
    #     method="get",
    #     filters={"state": "Established"},
    #     validation=ValidationRule(field="state", operator="!=", expected="Established")
    # )
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================


class ValidationRule(BaseModel):
    """Validation rule for threshold checking."""

    field: str = Field(description="Field to validate")
    operator: Literal["==", "!=", ">", "<", ">=", "<=", "in", "not_in"] = Field(
        default="!=", description="Comparison operator"
    )
    expected: Any = Field(description="Expected/threshold value")
    on_match: Literal["report_violation", "report_ok"] = Field(
        default="report_violation",
        description="Action when condition matches"
    )


class QueryPlan(BaseModel):
    """Compiled query plan from intent."""

    table: str = Field(description="SuzieQ table name (e.g., bgp, ospf, interfaces)")
    method: Literal["get", "summarize", "unique", "aver"] = Field(
        default="get", description="Query method"
    )
    filters: dict[str, Any] = Field(
        default_factory=dict, description="Query filters"
    )
    columns: list[str] = Field(
        default_factory=list, description="Columns to return (empty = all)"
    )
    validation: ValidationRule | None = Field(
        default=None, description="Threshold validation rule"
    )

    # Metadata
    compiled_from_intent: str = Field(default="", description="Original intent")
    confidence: float = Field(default=0.8, description="Compilation confidence")


class LLMCompilationResult(BaseModel):
    """LLM structured output for intent compilation."""

    table: str = Field(description="SuzieQ table name")
    method: Literal["get", "summarize", "unique", "aver"] = Field(default="get")
    filters: dict[str, Any] = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list)

    # Validation
    validation_field: str | None = Field(default=None)
    validation_operator: str = Field(default="!=")
    validation_expected: Any = Field(default=None)

    reasoning: str = Field(default="", description="Reasoning for the compilation")


# =============================================================================
# Prompt Template
# =============================================================================

INTENT_COMPILER_PROMPT = """你是网络运维专家。根据用户的检查意图，生成 SuzieQ 查询计划。

## 可用的 SuzieQ 表

| 表名 | 描述 | 常用字段 |
|------|------|----------|
| bgp | BGP 邻居状态 | hostname, peer, state, asn, peerAsn, vrf |
| ospf | OSPF 邻居状态 | hostname, ifname, state, area, nbrHostname |
| interfaces | 接口状态 | hostname, ifname, state, mtu, speed, errorsIn, errorsOut |
| routes | 路由表 | hostname, prefix, nexthopIps, protocol, vrf |
| macs | MAC 地址表 | hostname, macaddr, vlan, ifname |
| arpnd | ARP/ND 表 | hostname, ipAddress, macaddr, ifname |
| device | 设备信息 | hostname, model, vendor, version, uptime |
| lldp | LLDP 邻居 | hostname, ifname, peerHostname, peerIfname |
| vlan | VLAN 配置 | hostname, vlanId, vlanName, interfaces |

## 查询方法

- get: 获取原始数据
- summarize: 获取汇总统计
- unique: 获取唯一值
- aver: 断言/验证

## 检查意图

名称: {check_name}
描述: {intent}
严重级别: {severity}

## 输出要求

生成一个查询计划，包含：
1. table: 最相关的 SuzieQ 表
2. method: 查询方法 (通常用 get 或 summarize)
3. filters: 查询过滤条件
4. columns: 需要返回的列 (可选)
5. validation_field: 需要验证的字段
6. validation_operator: 验证操作符 (==, !=, >, <, >=, <=)
7. validation_expected: 期望值或阈值

## 示例

意图: "检查 BGP 邻居是否 Established"
→ table: "bgp", validation_field: "state", validation_operator: "!=", validation_expected: "Established"

意图: "检查接口是否有错误"
→ table: "interfaces", validation_field: "errorsIn", validation_operator: ">", validation_expected: 0

请基于上述意图生成查询计划。"""


# =============================================================================
# Intent Compiler
# =============================================================================


class IntentCompiler:
    """LLM-driven intent to query plan compiler.

    Compiles natural language inspection intents into structured SuzieQ
    query plans with validation rules.

    Features:
    - Schema-aware compilation using suzieq-schema context
    - Caching to avoid redundant LLM calls
    - Fallback to default plan on LLM failure

    Usage:
        compiler = IntentCompiler()
        plan = await compiler.compile(
            intent="检查 BGP 邻居状态",
            severity="critical"
        )
    """

    def __init__(
        self,
        cache_dir: Path | str = "data/cache/inspection_plans",
        enable_cache: bool = True,
    ) -> None:
        """Initialize compiler.

        Args:
            cache_dir: Directory to cache compiled plans.
            enable_cache: Whether to enable caching.
        """
        self.cache_dir = Path(cache_dir)
        self.enable_cache = enable_cache

        if enable_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.prompt = ChatPromptTemplate.from_template(INTENT_COMPILER_PROMPT)
        self._llm: BaseChatModel | None = None

    def _get_llm(self) -> BaseChatModel:
        """Lazy-load LLM with structured output."""
        if self._llm is None:
            from olav.core.llm import LLMFactory

            base_llm = LLMFactory.get_chat_model(json_mode=True)
            self._llm = base_llm.with_structured_output(LLMCompilationResult)
        return self._llm

    def _get_cache_key(self, intent: str, check_name: str, severity: str) -> str:
        """Generate cache key from intent parameters."""
        data = json.dumps({
            "intent": intent,
            "check_name": check_name,
            "severity": severity,
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def _load_from_cache(self, cache_key: str) -> QueryPlan | None:
        """Load compiled plan from cache."""
        if not self.enable_cache:
            return None

        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                return QueryPlan(**data)
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
        return None

    def _save_to_cache(self, cache_key: str, plan: QueryPlan) -> None:
        """Save compiled plan to cache."""
        if not self.enable_cache:
            return

        cache_file = self.cache_dir / f"{cache_key}.json"
        try:
            cache_file.write_text(
                plan.model_dump_json(indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    async def compile(
        self,
        intent: str,
        check_name: str = "",
        severity: str = "warning",
    ) -> QueryPlan:
        """Compile intent to query plan.

        Args:
            intent: Natural language inspection intent.
            check_name: Name of the check (for context).
            severity: Severity level (critical, warning, info).

        Returns:
            QueryPlan with table, filters, and validation rules.
        """
        # Check cache first
        cache_key = self._get_cache_key(intent, check_name, severity)
        cached = self._load_from_cache(cache_key)
        if cached:
            logger.info(f"[IntentCompiler] Cache hit: {check_name}")
            return cached

        logger.info(f"[IntentCompiler] Compiling: {intent[:50]}...")

        try:
            # Call LLM
            llm = self._get_llm()
            messages = self.prompt.format_messages(
                check_name=check_name or "unnamed",
                intent=intent,
                severity=severity,
            )

            result: LLMCompilationResult = await llm.ainvoke(messages)

            # Build QueryPlan
            validation = None
            if result.validation_field and result.validation_expected is not None:
                validation = ValidationRule(
                    field=result.validation_field,
                    operator=result.validation_operator,  # type: ignore
                    expected=result.validation_expected,
                )

            plan = QueryPlan(
                table=result.table,
                method=result.method,
                filters=result.filters,
                columns=result.columns,
                validation=validation,
                compiled_from_intent=intent,
                confidence=0.8,
            )

            # Cache result
            self._save_to_cache(cache_key, plan)

            logger.info(
                f"[IntentCompiler] Compiled: table={plan.table}, "
                f"method={plan.method}, validation={plan.validation}"
            )

            return plan

        except Exception as e:
            logger.error(f"[IntentCompiler] Compilation failed: {e}")

            # Fallback: try to infer from intent keywords
            return self._fallback_compile(intent, check_name, severity)

    def compile_sync(
        self,
        intent: str,
        check_name: str = "",
        severity: str = "warning",
    ) -> QueryPlan:
        """Synchronous version of compile."""
        import asyncio
        return asyncio.run(self.compile(intent, check_name, severity))

    def _fallback_compile(
        self,
        intent: str,
        check_name: str,
        severity: str,
    ) -> QueryPlan:
        """Fallback compilation using keyword matching."""
        intent_lower = intent.lower()

        # Keyword to table mapping
        table_keywords = {
            "bgp": ["bgp", "邻居", "neighbor", "peer", "as"],
            "ospf": ["ospf", "ospf邻居", "area"],
            "interfaces": ["接口", "interface", "端口", "port", "错误", "error"],
            "routes": ["路由", "route", "路由表"],
            "device": ["设备", "device", "cpu", "内存", "memory", "uptime"],
            "macs": ["mac", "mac地址"],
            "lldp": ["lldp", "cdp", "拓扑"],
            "vlan": ["vlan"],
        }

        # Find best matching table
        table = "device"  # default
        for tbl, keywords in table_keywords.items():
            if any(kw in intent_lower for kw in keywords):
                table = tbl
                break

        logger.warning(
            f"[IntentCompiler] Using fallback: table={table} for intent={intent[:30]}"
        )

        return QueryPlan(
            table=table,
            method="summarize",
            filters={},
            validation=None,
            compiled_from_intent=intent,
            confidence=0.3,  # Low confidence for fallback
        )

    def clear_cache(self) -> int:
        """Clear all cached plans.

        Returns:
            Number of cache files deleted.
        """
        if not self.cache_dir.exists():
            return 0

        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
            count += 1

        logger.info(f"[IntentCompiler] Cleared {count} cached plans")
        return count
