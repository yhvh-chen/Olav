"""Skill Router - LLM驱动的技能路由和意图过滤.

P3优化: 合并Guard过滤和Skill选择为单次LLM调用，减少50%延迟。
"""

import json
import logging
from typing import Any

from langchain_core.language_models import BaseLanguageModel

from olav.core.skill_loader import Skill, SkillLoader

logger = logging.getLogger(__name__)


class SkillRouter:
    """技能路由器 - P3优化: 单次LLM调用完成Guard+Skill选择."""

    def __init__(self, llm: BaseLanguageModel, skill_loader: SkillLoader) -> None:
        self.llm = llm
        self.skill_loader = skill_loader

    def route(self, user_query: str) -> dict[str, Any]:
        """路由用户查询到合适的技能 (P3优化: 单次LLM调用).

        返回格式:
        {
            "selected_skill": Skill | None,
            "reason": str,
            "is_network_related": bool,
            "confidence": float,
            "fallback": bool  # 是否使用fallback
        }
        """
        # 加载skill索引
        skill_index = self.skill_loader.load_all()
        if not skill_index:
            logger.warning("No skills loaded")
            return {
                "selected_skill": None,
                "reason": "No skills available",
                "is_network_related": True,
                "confidence": 0.0,
                "fallback": False,
            }

        # P3优化: 单次LLM调用同时完成Guard过滤和Skill选择
        result = self._unified_route(user_query, skill_index)

        if not result["is_network_related"]:
            return {
                "selected_skill": None,
                "reason": result["reason"],
                "is_network_related": False,
                "confidence": 0.0,
                "fallback": False,
            }

        if result["skill_id"] and result["confidence"] >= 0.5:
            # 成功匹配
            selected_skill = self.skill_loader.get_skill(result["skill_id"])
            return {
                "selected_skill": selected_skill,
                "reason": result["reason"],
                "is_network_related": True,
                "confidence": result["confidence"],
                "fallback": False,
            }
        else:
            # 无匹配或置信度低 → 降级到 quick-query
            fallback_skill = self.skill_loader.get_skill("quick-query")
            return {
                "selected_skill": fallback_skill,
                "reason": f"Fallback: {result.get('reason', 'Low confidence')}",
                "is_network_related": True,
                "confidence": result.get("confidence", 0.0),
                "fallback": True,
            }
    def _unified_route(self, user_query: str, skill_index: dict[str, Skill]) -> dict[str, Any]:
        """P3优化: 统一路由 - 单次LLM调用完成Guard+Skill选择.

        返回:
        {
            "is_network_related": bool,
            "skill_id": str | None,
            "confidence": float,
            "reason": str
        }
        """
        skill_descriptions = self._format_skill_descriptions(skill_index)

        unified_prompt = f"""你是网络运维AI助手的智能路由器。一步完成意图判断和技能选择。

## 第一步: 判断是否为网络运维相关问题

网络运维相关 (is_network_related=true):
- 设备查询 (接口、路由、BGP、OSPF、VLAN、MAC、ARP)
- 故障排查 (ping不通、丢包、延迟)
- 配置检查、设备巡检、网络拓扑
- 任何涉及网络设备的问题

非网络相关 (is_network_related=false):
- 闲聊、天气、编程、通用知识、其他领域

## 第二步: 如果网络相关，选择最合适的技能

可用技能:
{skill_descriptions}

选择依据:
- 简单查询 → quick-query (接口、版本、状态)
- 故障诊断 → network-diagnosis (ping不通、为什么)
- 设备巡检 → device-inspection (健康检查、巡检)
- 深度分析 → deep-analysis (复杂问题、多设备)
- 配置操作 → configuration-management (配置、修改)

## 用户问题
{user_query}

## 回复 (仅JSON，无其他内容)
{{
  "is_network_related": true/false,
  "skill_id": "技能ID或null (仅当is_network_related=true)",
  "confidence": 0-1之间的置信度,
  "reason": "简短理由"
}}"""

        try:
            response = self.llm.invoke(unified_prompt)
            result = json.loads(response.content)
            return {
                "is_network_related": result.get("is_network_related", True),
                "skill_id": result.get("skill_id"),
                "confidence": result.get("confidence", 0.0),
                "reason": result.get("reason", ""),
            }
        except Exception as e:
            logger.error(f"Unified routing error: {e}")
            # 异常时保守处理: 假设网络相关，使用quick-query
            return {
                "is_network_related": True,
                "skill_id": "quick-query",
                "confidence": 0.5,
                "reason": f"Fallback due to error: {e}",
            }

    def _format_skill_descriptions(self, skill_index: dict[str, Skill]) -> str:
        """格式化skill描述用于LLM."""
        descriptions = []
        for skill_id, skill in skill_index.items():
            desc = f"""- **{skill_id}** ({skill.complexity})
  说明: {skill.description}
  意图: {skill.intent}
  示例: {", ".join(skill.examples[:3]) if skill.examples else "无"}"""
            descriptions.append(desc)

        return "\n".join(descriptions)


def create_skill_router(llm: BaseLanguageModel, skill_loader: SkillLoader) -> SkillRouter:
    """创建技能路由器."""
    return SkillRouter(llm, skill_loader)
