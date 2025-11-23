from __future__ import annotations

"""Schema-Aware dynamic configuration compliance evaluator.

Phase 2 Dynamic Audit Design:
  Instead of hardcoding protocol rules (MPLS/BGP/OSPF/etc.), leverage
  OLAV's existing Schema-Aware architecture:

  1. Field Semantic Relevance (already in Deep Dive _validate_field_relevance)
  2. Data Presence Validation (empty vs non-empty results)
  3. Schema Investigation Results (feasibility classification)

This eliminates code proliferation and reuses anti-hallucination mechanisms.

Objective Validation Strategy:
  - Check execution_output has data (not empty/error)
  - Verify returned fields are semantically relevant to task
  - Confirm data count/structure meets minimum expectations
  - Flag indeterminate cases (no evaluator rule = auto-pass if data exists)

Integration:
  1. execute_todo_node calls evaluate(todo, execution_output)
  2. Returns EvaluationResult with passed/score/feedback
  3. Workflow stores evaluation_passed/evaluation_score/failure_reason
  4. Final summary aggregates pass/fail statistics

NOTE: This evaluator does NOT re-query devices - it only validates
the execution_output structure/content produced by tools.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


@dataclass(slots=True)
class EvaluationResult:
    passed: bool
    score: float
    feedback: str
    details: Optional[Dict[str, Any]] = None


class TaskEvaluatorProtocol(Protocol):  # For future polymorphism / DI
    async def evaluate(self, task: Dict[str, Any], execution_output: Dict[str, Any]) -> EvaluationResult: ...


class ConfigComplianceEvaluator(TaskEvaluatorProtocol):
    """Schema-Aware dynamic evaluator - no hardcoded protocol rules."""

    async def evaluate(
        self, task: Dict[str, Any], execution_output: Dict[str, Any]
    ) -> EvaluationResult:
        """Dynamic evaluation based on schema and data structure.
        
        Strategy:
          1. Check execution status (SCHEMA_NOT_FOUND/NO_DATA_FOUND/etc)
          2. Validate data existence (non-empty result)
          3. Check field semantic relevance (task keywords vs returned columns)
          4. Conservative scoring: data presence + relevance = pass
        
        This approach works for ANY protocol/feature without hardcoding rules.
        """
        # Step 1: Check execution status (reuse Deep Dive classification)
        status = execution_output.get("status")
        if status in {"SCHEMA_NOT_FOUND", "DATA_NOT_RELEVANT", "TOOL_ERROR"}:
            return EvaluationResult(
                passed=False,
                score=0.0,
                feedback=f"Execution failed: {status}",
                details={"status": status, "message": execution_output.get("message")},
            )
        
        if status == "NO_DATA_FOUND":
            # Empty result - could be legitimate (no config) or error
            # Use task context to decide
            task_text = task.get("task", "").lower()
            if any(kw in task_text for kw in ["审计", "检查", "audit", "check", "verify"]):
                # Audit tasks expect data - empty = fail
                return EvaluationResult(
                    passed=False,
                    score=0.0,
                    feedback="审计任务未返回数据，可能配置缺失或查询表错误",
                    details={"status": "NO_DATA_FOUND"},
                )
            else:
                # Query tasks - empty may be legitimate
                return EvaluationResult(
                    passed=True,
                    score=0.5,  # Partial score - query succeeded but no data
                    feedback="查询成功，但无相关数据",
                    details={"status": "NO_DATA_FOUND"},
                )
        
        # Step 2: Validate data existence
        data = execution_output.get("data")
        if not data or (isinstance(data, list) and len(data) == 0):
            return EvaluationResult(
                passed=False,
                score=0.0,
                feedback="执行输出无数据（data 字段为空）",
                details={"data_type": type(data).__name__},
            )
        
        # Step 3: Field semantic relevance check (reuse Deep Dive logic)
        columns = execution_output.get("columns", [])
        queried_table = execution_output.get("table", "unknown")
        task_text = task.get("task", "")
        
        if columns and not self._validate_field_relevance(task_text, columns, queried_table):
            return EvaluationResult(
                passed=False,
                score=0.3,  # Partial - data exists but may not be relevant
                feedback=f"返回字段与任务语义不匹配。任务关键词: {self._extract_task_keywords(task_text)}, 返回字段: {columns[:5]}",
                details={"columns": columns, "table": queried_table},
            )
        
        # Step 4: Success - data exists and appears relevant
        data_count = len(data) if isinstance(data, list) else 1
        return EvaluationResult(
            passed=True,
            score=1.0,
            feedback=f"数据验证通过：返回 {data_count} 条记录，字段语义相关",
            details={"count": data_count, "table": queried_table, "columns": columns[:10]},
        )
    
    def _validate_field_relevance(self, task_text: str, returned_columns: list[str], queried_table: str) -> bool:
        """Validate if returned columns are semantically relevant to task.
        
        Reuses Deep Dive's anti-hallucination logic with improvements:
        - Table name match counts as relevant (e.g. 'bgp' table for BGP task)
        - Generic tables (device/interfaces/routes) accepted only if no specific protocol mentioned
        - Column keyword match also validates relevance
        """
        task_keywords = self._extract_task_keywords(task_text)
        columns_str = " ".join(returned_columns).lower()
        
        # Check 1: Table name matches task keyword (e.g. bgp table for BGP task)
        if task_keywords and queried_table.lower() in task_keywords:
            return True
        
        # Check 2: Any task keywords appear in field names
        matches = sum(1 for kw in task_keywords if kw in columns_str)
        if matches > 0:
            return True
        
        # Check 3: Generic inventory tables acceptable ONLY if no specific protocol mentioned
        # (prevents device table from matching MPLS audit tasks)
        if queried_table in {"device", "interfaces", "routes"}:
            # If task mentions specific protocols, generic table is NOT relevant
            if task_keywords:
                return False  # Has protocol keywords but using generic table = mismatch
            return True  # Generic query without protocol keywords = acceptable
        
        return False
    
    def _extract_task_keywords(self, task_text: str) -> list[str]:
        """Extract technical keywords from task description."""
        lower = task_text.lower()
        keywords = [
            "mpls", "ldp", "rsvp", "bgp", "ospf", "eigrp", "isis",
            "vlan", "vxlan", "evpn", "interface", "route", "prefix",
            "neighbor", "peer", "session", "tunnel", "policy",
            "qos", "acl", "nat", "firewall", "vpn", "lldp", "mac"
        ]
        return [kw for kw in keywords if kw in lower]


__all__ = [
    "EvaluationResult",
    "TaskEvaluatorProtocol",
    "ConfigComplianceEvaluator",
]
