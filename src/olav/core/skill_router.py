"""Skill Router - LLM驱动的技能路由和意图过滤."""

import json
import logging
from typing import Optional, Dict, Any
from langchain_core.language_models import BaseLanguageModel

from olav.core.skill_loader import SkillLoader, Skill

logger = logging.getLogger(__name__)


class SkillRouter:
    """技能路由器 - Guard意图过滤 + LLM语义匹配."""

    def __init__(self, llm: BaseLanguageModel, skill_loader: SkillLoader):
        self.llm = llm
        self.skill_loader = skill_loader

    def route(self, user_query: str) -> Dict[str, Any]:
        """路由用户查询到合适的技能.

        返回格式:
        {
            "selected_skill": Skill | None,
            "reason": str,
            "is_network_related": bool,
            "confidence": float,
            "fallback": bool  # 是否使用fallback
        }
        """
        # Step 1: Guard 意图过滤
        guard_result = self._guard_filter(user_query)
        if not guard_result["is_network_related"]:
            return {
                "selected_skill": None,
                "reason": guard_result["reason"],
                "is_network_related": False,
                "confidence": 0.0,
                "fallback": False,
            }

        # Step 2: 加载skill索引
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

        # Step 3: LLM 路由选择 Skill
        llm_result = self._llm_select_skill(user_query, skill_index)

        if llm_result["skill_id"] and llm_result["confidence"] >= 0.5:
            # 成功匹配
            selected_skill = self.skill_loader.get_skill(llm_result["skill_id"])
            return {
                "selected_skill": selected_skill,
                "reason": llm_result["reason"],
                "is_network_related": True,
                "confidence": llm_result["confidence"],
                "fallback": False,
            }
        else:
            # 无匹配或置信度低 → 降级到 quick-query
            fallback_skill = self.skill_loader.get_skill("quick-query")
            return {
                "selected_skill": fallback_skill,
                "reason": f"Fallback: {llm_result.get('reason', 'Low confidence')}",
                "is_network_related": True,
                "confidence": llm_result.get("confidence", 0.0),
                "fallback": True,
            }

    def _guard_filter(self, user_query: str) -> Dict[str, Any]:
        """Guard 层 - 判断是否为网络运维相关问题.

        返回:
        {
            "is_network_related": bool,
            "reason": str  # 拒绝理由（如果不相关）
        }
        """
        guard_prompt = f"""你是网络运维 AI 助手的意图过滤器。

判断以下问题是否为网络运维相关。

## 网络运维相关问题 (返回 true)
- 查询设备状态 (接口、路由、BGP、OSPF)
- 故障排查 (ping不通、丢包、延迟高)
- 配置检查 (VLAN、ACL、路由策略)
- 设备巡检 (健康检查、告警查询)
- 网络拓扑相关
- IP/MAC/ARP查询
- 任何涉及网络设备的问题

## 非网络运维问题 (返回 false)
- 闲聊 ("你好"、"今天天气怎么样")
- 编程问题 ("写个Python脚本")
- 通用知识 ("什么是人工智能")
- 其他领域 ("数据库怎么优化")

## 用户问题
{user_query}

## 回复 (仅JSON，无其他内容)
返回格式: {{"is_network_related": true/false}}"""

        try:
            response = self.llm.invoke(guard_prompt)
            result = json.loads(response.content)
            is_related = result.get("is_network_related", False)

            return {
                "is_network_related": is_related,
                "reason": ""
                if is_related
                else "我是网络运维AI助手，这个问题超出我的专业范围。请提问网络相关问题。",
            }
        except Exception as e:
            logger.error(f"Guard filter error: {e}")
            # 异常时保守判断，假设是网络相关
            return {"is_network_related": True, "reason": ""}

    def _llm_select_skill(
        self, user_query: str, skill_index: Dict[str, Skill]
    ) -> Dict[str, Any]:
        """LLM 选择最合适的 Skill.

        返回:
        {
            "skill_id": str | None,
            "confidence": float,
            "reason": str
        }
        """
        # 构建skill描述
        skill_descriptions = self._format_skill_descriptions(skill_index)

        routing_prompt = f"""你是网络运维AI助手的技能路由器。

## 可用技能 (Skill)
{skill_descriptions}

## 用户问题
{user_query}

## 任务
根据问题选择最合适的技能。考虑以下因素：
1. 问题复杂度 (简单 → simple, 复杂 → complex)
2. 问题类型 (query/diagnose/inspect/config)
3. 是否与示例相似
4. 技能适用场景

## 回复 (仅JSON，无其他内容)
返回格式:
{{
  "skill_id": "选中的技能ID (或null)",
  "confidence": 0-1之间的置信度,
  "reason": "选择理由"
}}"""

        try:
            response = self.llm.invoke(routing_prompt)
            result = json.loads(response.content)
            return {
                "skill_id": result.get("skill_id"),
                "confidence": result.get("confidence", 0.0),
                "reason": result.get("reason", ""),
            }
        except Exception as e:
            logger.error(f"LLM skill selection error: {e}")
            return {"skill_id": None, "confidence": 0.0, "reason": str(e)}

    def _format_skill_descriptions(self, skill_index: Dict[str, Skill]) -> str:
        """格式化skill描述用于LLM."""
        descriptions = []
        for skill_id, skill in skill_index.items():
            desc = f"""- **{skill_id}** ({skill.complexity})
  说明: {skill.description}
  意图: {skill.intent}
  示例: {', '.join(skill.examples[:3]) if skill.examples else '无'}"""
            descriptions.append(desc)

        return "\n".join(descriptions)


def create_skill_router(
    llm: BaseLanguageModel, skill_loader: SkillLoader
) -> SkillRouter:
    """创建技能路由器."""
    return SkillRouter(llm, skill_loader)
