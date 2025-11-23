import pytest

from olav.evaluators.config_compliance import ConfigComplianceEvaluator, EvaluationResult

pytestmark = pytest.mark.asyncio


async def test_data_exists_and_relevant():
    """Schema-Aware dynamic evaluation: data present + fields relevant = pass."""
    evaluator = ConfigComplianceEvaluator()
    task = {
        "id": 1,
        "task": "检查所有设备的 BGP 配置",
    }
    execution_output = {
        "table": "bgp",
        "columns": ["hostname", "peer", "asn", "state"],
        "data": [{"hostname": "R1", "peer": "10.0.0.2", "asn": 65001, "state": "Estd"}],
    }
    result: EvaluationResult = await evaluator.evaluate(task, execution_output)
    assert result.passed is True
    assert result.score == 1.0
    assert "验证通过" in result.feedback or "记录" in result.feedback


async def test_data_exists_but_not_relevant():
    """Data returned but fields semantically irrelevant to task = partial fail."""
    evaluator = ConfigComplianceEvaluator()
    task = {
        "id": 2,
        "task": "审计 MPLS LDP 配置",
    }
    # Query returned device table (generic) instead of MPLS-related table
    execution_output = {
        "table": "device",  # Not in allowed generic list for MPLS task
        "columns": ["hostname", "version", "model"],  # No MPLS keywords
        "data": [{"hostname": "R1", "version": "15.0", "model": "ASR9k"}],
    }
    result: EvaluationResult = await evaluator.evaluate(task, execution_output)
    # Should fail or partial score due to semantic mismatch
    assert result.score < 1.0  # Either 0.0 or 0.3
    assert "不匹配" in result.feedback or "关键词" in result.feedback


async def test_no_data_found_audit_task():
    """Audit tasks with NO_DATA_FOUND should fail."""
    evaluator = ConfigComplianceEvaluator()
    task = {
        "id": 3,
        "task": "审计所有边界路由器的 OSPF 配置",
    }
    execution_output = {"status": "NO_DATA_FOUND"}
    result: EvaluationResult = await evaluator.evaluate(task, execution_output)
    assert result.passed is False
    assert result.score == 0.0
    assert "审计" in result.feedback or "未返回数据" in result.feedback


async def test_no_data_found_query_task():
    """Query tasks with NO_DATA_FOUND may be legitimate (partial pass)."""
    evaluator = ConfigComplianceEvaluator()
    task = {
        "id": 4,
        "task": "查询 R1 的 ISIS 邻居",
    }
    execution_output = {"status": "NO_DATA_FOUND"}
    result: EvaluationResult = await evaluator.evaluate(task, execution_output)
    # Query tasks get partial credit
    assert result.passed is True
    assert result.score == 0.5
    assert "查询成功" in result.feedback or "无相关数据" in result.feedback


async def test_schema_not_found():
    """SCHEMA_NOT_FOUND status should always fail."""
    evaluator = ConfigComplianceEvaluator()
    task = {
        "id": 5,
        "task": "检查 EVPN 配置",
    }
    execution_output = {"status": "SCHEMA_NOT_FOUND", "message": "Table 'evpn' not in schema"}
    result: EvaluationResult = await evaluator.evaluate(task, execution_output)
    assert result.passed is False
    assert result.score == 0.0
    assert "SCHEMA_NOT_FOUND" in result.feedback or "failed" in result.feedback.lower()


async def test_generic_inventory_table_always_relevant():
    """Generic tables (device/interfaces/routes) should pass relevance check."""
    evaluator = ConfigComplianceEvaluator()
    task = {
        "id": 6,
        "task": "审计所有设备状态",
    }
    execution_output = {
        "table": "device",
        "columns": ["hostname", "status", "uptime"],
        "data": [{"hostname": "R1", "status": "alive", "uptime": 86400}],
    }
    result: EvaluationResult = await evaluator.evaluate(task, execution_output)
    assert result.passed is True
    assert result.score == 1.0
