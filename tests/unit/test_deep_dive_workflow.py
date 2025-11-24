"""Unit tests for Deep Dive Workflow.

Tests:
1. task_planning_node: LLM todo generation
2. schema_investigation_node: feasibility classification
3. execute_todo_node: External Evaluator integration
4. recursive_check_node: recursion logic (when implemented)
5. HITL interrupt/resume flow
"""

import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from olav.workflows.deep_dive import DeepDiveWorkflow, DeepDiveState, TodoItem, ExecutionPlan


class TestDeepDiveWorkflow:
    """Test Deep Dive Workflow components."""
    
    @pytest.fixture
    def workflow(self):
        """Create workflow instance with mocked LLM."""
        with patch('olav.workflows.deep_dive.LLMFactory') as mock_factory:
            # Mock both normal and JSON LLMs
            mock_llm = AsyncMock()
            mock_llm_json = AsyncMock()
            mock_factory.get_chat_model.side_effect = lambda json_mode=False: (
                mock_llm_json if json_mode else mock_llm
            )
            
            workflow = DeepDiveWorkflow()
            workflow.llm = mock_llm
            workflow.llm_json = mock_llm_json
            return workflow
    
    @pytest.fixture
    def initial_state(self) -> DeepDiveState:
        """Create initial workflow state."""
        return DeepDiveState(
            messages=[HumanMessage(content="审计所有边界路由器的 BGP 配置")],
            todos=[],
            execution_plan=None,
            current_todo_id=None,
            completed_results={},
            recursion_depth=0,
            max_depth=3,
            expert_mode=True
        )
    
    @pytest.mark.asyncio
    async def test_validate_input_audit_trigger(self, workflow):
        """Test Deep Dive validation detects audit keywords."""
        valid_queries = [
            "审计所有边界路由器的 BGP 配置",
            "audit all core switches",
            "批量检查接口状态",
            "为什么数据中心 A 无法访问数据中心 B",
            "深入分析 OSPF 邻居关系异常",
        ]
        
        for query in valid_queries:
            is_valid, reason = await workflow.validate_input(query)
            assert is_valid, f"Query should trigger Deep Dive: {query}"
            assert "trigger" in reason.lower()
    
    @pytest.mark.asyncio
    async def test_validate_input_simple_query_rejected(self, workflow):
        """Test simple queries are rejected for Deep Dive."""
        invalid_queries = [
            "查询 R1 接口状态",
            "show bgp summary",
            "获取设备列表",
        ]
        
        for query in invalid_queries:
            is_valid, reason = await workflow.validate_input(query)
            assert not is_valid, f"Simple query should not trigger Deep Dive: {query}"
    
    @pytest.mark.asyncio
    async def test_task_planning_node_generates_todos(self, workflow, initial_state):
        """Test task planning node generates structured Todo List from LLM."""
        # Mock LLM JSON response
        mock_response = AsyncMock()
        mock_response.content = """
        {
            "todos": [
                {"id": 1, "task": "查询所有边界路由器设备列表", "deps": []},
                {"id": 2, "task": "检查 BGP 会话状态", "deps": [1]},
                {"id": 3, "task": "验证 BGP 安全配置", "deps": [1, 2]}
            ]
        }
        """
        workflow.llm_json.ainvoke = AsyncMock(return_value=mock_response)
        
        # Execute node
        result = await workflow.task_planning_node(initial_state)
        
        # Verify todos generated
        assert "todos" in result
        assert len(result["todos"]) == 3
        assert result["todos"][0]["id"] == 1
        assert result["todos"][0]["status"] == "pending"
        assert result["todos"][2]["deps"] == [1, 2]
        assert result["recursion_depth"] == 0
        assert result["max_depth"] == 3
    
    @pytest.mark.asyncio
    async def test_task_planning_node_fallback_on_invalid_json(self, workflow, initial_state):
        """Test fallback to single todo when LLM returns invalid JSON."""
        # Mock invalid JSON response
        mock_response = AsyncMock()
        mock_response.content = "Invalid JSON"
        workflow.llm_json.ainvoke = AsyncMock(return_value=mock_response)
        
        # Execute node
        result = await workflow.task_planning_node(initial_state)
        
        # Verify fallback to single todo
        assert len(result["todos"]) == 1
        assert result["todos"][0]["task"] == "审计所有边界路由器的 BGP 配置"
    
    @pytest.mark.asyncio
    async def test_schema_investigation_node_classifies_feasible(self, workflow, initial_state):
        """Test schema investigation classifies feasible tasks correctly."""
        # Setup state with todos
        initial_state["todos"] = [
            TodoItem(
                id=1,
                task="查询所有设备 device 表",
                status="pending",
                result=None,
                deps=[],
                feasibility=None,
                recommended_table=None,
                schema_notes=None,
                evaluation_passed=None,
                evaluation_score=None,
                failure_reason=None
            ),
            TodoItem(
                id=2,
                task="检查接口状态 interfaces 表",
                status="pending",
                result=None,
                deps=[],
                feasibility=None,
                recommended_table=None,
                schema_notes=None,
                evaluation_passed=None,
                evaluation_score=None,
                failure_reason=None
            )
        ]
        
        # Mock suzieq_schema_search to return available tables
        mock_schema_result_device = {
            "tables": ["device", "interfaces", "bgp"],
            "device": {"fields": ["hostname", "version", "model", "vendor"]}
        }
        mock_schema_result_interfaces = {
            "tables": ["interfaces", "bgp", "routes"],
            "interfaces": {"fields": ["hostname", "ifname", "state", "ipAddressList"]}
        }
        
        # Patch actual tool module (local import inside workflow methods)
        with patch('olav.tools.suzieq_parquet_tool.suzieq_schema_search') as mock_search:
            # Return different results based on query
            async def mock_ainvoke(args):
                query = args.get("query", "")
                if "device" in query.lower():
                    return mock_schema_result_device
                elif "interface" in query.lower():
                    return mock_schema_result_interfaces
                return {"tables": []}
            
            mock_search.ainvoke = AsyncMock(side_effect=mock_ainvoke)
            
            # Execute node
            result = await workflow.schema_investigation_node(initial_state)
        
        # Verify execution plan
        assert result["execution_plan"] is not None
        plan: ExecutionPlan = result["execution_plan"]
        
        # Both tasks should be feasible (heuristic matches schema)
        assert len(plan["feasible_tasks"]) >= 1
        assert 1 in plan["feasible_tasks"] or 2 in plan["feasible_tasks"]
        
        # Check todos updated with feasibility info
        todos = result["todos"]
        assert any(t["feasibility"] == "feasible" for t in todos)
        assert any(t["recommended_table"] is not None for t in todos)
    
    @pytest.mark.asyncio
    async def test_schema_investigation_node_classifies_infeasible(self, workflow, initial_state):
        """Test schema investigation marks tasks as infeasible when no schema match."""
        # Setup state with todo for unsupported feature
        initial_state["todos"] = [
            TodoItem(
                id=1,
                task="查询 MPLS LDP 配置",
                status="pending",
                result=None,
                deps=[],
                feasibility=None,
                recommended_table=None,
                schema_notes=None,
                evaluation_passed=None,
                evaluation_score=None,
                failure_reason=None
            )
        ]
        
        # Mock schema search returning no tables
        with patch('olav.tools.suzieq_parquet_tool.suzieq_schema_search') as mock_search:
            mock_search.ainvoke = AsyncMock(return_value={"tables": []})
            
            # Execute node
            result = await workflow.schema_investigation_node(initial_state)
        
        # Verify task marked as infeasible
        plan: ExecutionPlan = result["execution_plan"]
        assert 1 in plan["infeasible_tasks"]
        assert plan["user_approval_required"] is True
        
        # Check todo updated
        todo = result["todos"][0]
        assert todo["feasibility"] == "infeasible"
        assert "NETCONF" in plan["recommendations"][1]
    
    @pytest.mark.asyncio
    async def test_execute_todo_node_with_valid_table(self, workflow, initial_state):
        """Test execute_todo_node successfully executes with valid table."""
        initial_state["todos"] = [
            TodoItem(
                id=1,
                task="查询所有设备",
                status="pending",
                result=None,
                deps=[],
                feasibility="feasible",
                recommended_table="device",
                schema_notes="✅ 表 'device' 可用",
                evaluation_passed=None,
                evaluation_score=None,
                failure_reason=None,
            )
        ]
        mock_query_result = {
            "status": "OK",
            "table": "device",
            "columns": ["hostname", "version", "model"],
            "data": [
                {"hostname": "R1", "version": "15.0", "model": "CSR1000v"},
                {"hostname": "R2", "version": "16.0", "model": "ASR9000"},
            ],
            "count": 2,
        }
        mock_schema_result = {
            "tables": ["device", "interfaces", "bgp"],
            "device": {"fields": ["hostname", "version", "model"]},
        }
        with patch("olav.tools.suzieq_parquet_tool.suzieq_query") as mock_query, \
             patch("olav.tools.suzieq_parquet_tool.suzieq_schema_search") as mock_schema, \
             patch("olav.evaluators.config_compliance.ConfigComplianceEvaluator") as mock_evaluator_class:
            mock_query.ainvoke = AsyncMock(return_value=mock_query_result)
            mock_schema.ainvoke = AsyncMock(return_value=mock_schema_result)
            mock_evaluator = AsyncMock()
            mock_eval_result = MagicMock(passed=True, score=1.0, feedback="Data valid")
            mock_evaluator.evaluate = AsyncMock(return_value=mock_eval_result)
            mock_evaluator_class.return_value = mock_evaluator
            result = await workflow.execute_todo_node(initial_state)
        assert result["todos"][0]["status"] == "completed"
        assert result["todos"][0]["result"] and "TOOL_CALL" in result["todos"][0]["result"]
        assert result["todos"][0]["evaluation_passed"] is True
        assert result["todos"][0]["evaluation_score"] == 1.0
    
    @pytest.mark.asyncio
    async def test_execute_todo_node_schema_not_found(self, workflow, initial_state):
        """Test execute_todo_node handles SCHEMA_NOT_FOUND error."""
        # Setup state
        initial_state["todos"] = [
            TodoItem(
                id=1,
                task="检查 BGP 邻居状态",  # Heuristic maps to bgp
                status="pending",
                result=None,
                deps=[],
                feasibility=None,
                recommended_table=None,
                schema_notes=None,
                evaluation_passed=None,
                evaluation_score=None,
                failure_reason=None,
            )
        ]
        
        # Mock schema search returning empty (table not found)
        with patch('olav.tools.suzieq_parquet_tool.suzieq_schema_search') as mock_schema:
            # Return schema without 'bgp' to simulate missing table
            mock_schema.ainvoke = AsyncMock(return_value={"tables": ["device", "interfaces"]})
            
            # Execute node (will try to query non-existent table and fail)
            result = await workflow.execute_todo_node(initial_state)
        
        # Verify todo marked as failed
        assert result["todos"][0]["status"] == "failed"
        assert "SCHEMA_NOT_FOUND" in result["todos"][0]["result"]
    
    @pytest.mark.asyncio
    async def test_execute_todo_node_evaluator_integration(self, workflow, initial_state):
        """Test External Evaluator integration in execute_todo_node."""
        initial_state["todos"] = [
            TodoItem(
                id=1,
                task="检查 BGP 会话",
                status="pending",
                result=None,
                deps=[],
                feasibility="feasible",
                recommended_table="bgp",
                schema_notes="✅ 表 'bgp' 可用",
                evaluation_passed=None,
                evaluation_score=None,
                failure_reason=None,
            )
        ]
        mock_query_result = {
            "status": "OK",
            "table": "bgp",
            "columns": ["hostname", "bgpPeer", "state"],  # include 'bgp' for relevance
            "data": [{"hostname": "R1", "bgpPeer": "10.0.0.2", "state": "Established"}],
            "count": 1,
        }
        mock_schema_result = {"tables": ["bgp"], "bgp": {"fields": ["hostname", "peer", "state"]}}
        with patch("olav.tools.suzieq_parquet_tool.suzieq_query") as mock_query, \
             patch("olav.tools.suzieq_parquet_tool.suzieq_schema_search") as mock_schema, \
             patch("olav.evaluators.config_compliance.ConfigComplianceEvaluator") as mock_evaluator_class:
            mock_query.ainvoke = AsyncMock(return_value=mock_query_result)
            mock_schema.ainvoke = AsyncMock(return_value=mock_schema_result)
            mock_evaluator = AsyncMock()
            mock_eval_result = MagicMock(passed=False, score=0.5, feedback="Missing expected BGP peers")
            mock_evaluator.evaluate = AsyncMock(return_value=mock_eval_result)
            mock_evaluator_class.return_value = mock_evaluator
            result = await workflow.execute_todo_node(initial_state)
        assert result["todos"][0]["evaluation_passed"] is False
        assert result["todos"][0]["evaluation_score"] == 0.5
        assert "Missing expected BGP peers" in (result["todos"][0]["failure_reason"] or "")
    
    @pytest.mark.asyncio
    async def test_execute_todo_node_respects_dependencies(self, workflow, initial_state):
        """Test execute_todo_node respects todo dependencies."""
        initial_state["todos"] = [
            TodoItem(
                id=1,
                task="获取设备列表",
                status="pending",
                result=None,
                deps=[],
                feasibility=None,
                recommended_table=None,
                schema_notes=None,
                evaluation_passed=None,
                evaluation_score=None,
                failure_reason=None,
            ),
            TodoItem(
                id=2,
                task="检查设备配置",
                status="pending",
                result=None,
                deps=[1],
                feasibility=None,
                recommended_table=None,
                schema_notes=None,
                evaluation_passed=None,
                evaluation_score=None,
                failure_reason=None,
            ),
        ]
        with patch("olav.tools.suzieq_parquet_tool.suzieq_query") as mock_query, \
             patch("olav.tools.suzieq_parquet_tool.suzieq_schema_search") as mock_schema:
            mock_schema.ainvoke = AsyncMock(return_value={"tables": ["device"]})
            mock_query.ainvoke = AsyncMock(return_value={
                "status": "OK",
                "table": "device",
                "columns": ["hostname"],
                "data": [{"hostname": "R1"}],
                "count": 1,
            })
            result1 = await workflow.execute_todo_node(initial_state)
        assert result1["todos"][0]["status"] in ["in-progress", "completed"]
        assert result1["todos"][1]["status"] == "pending"
    
    def test_format_execution_plan(self, workflow):
        """Test execution plan formatting for user display."""
        todos = [
            TodoItem(
                id=1,
                task="查询设备",
                status="pending",
                result=None,
                deps=[],
                feasibility="feasible",
                recommended_table="device",
                schema_notes="✅ 表 'device' 可用",
                evaluation_passed=None,
                evaluation_score=None,
                failure_reason=None
            ),
            TodoItem(
                id=2,
                task="查询 MPLS",
                status="pending",
                result=None,
                deps=[],
                feasibility="infeasible",
                recommended_table=None,
                schema_notes="❌ 无对应表",
                evaluation_passed=None,
                evaluation_score=None,
                failure_reason=None
            )
        ]
        
        plan: ExecutionPlan = {
            "feasible_tasks": [1],
            "uncertain_tasks": [],
            "infeasible_tasks": [2],
            "recommendations": {
                1: "使用 suzieq_query(table='device')",
                2: "建议使用 NETCONF 查询"
            },
            "user_approval_required": True
        }
        
        formatted = workflow._format_execution_plan(todos, plan)
        
        # Verify formatting
        assert "✅ 可执行任务" in formatted
        assert "❌ 无法执行任务" in formatted
        assert "任务 1" in formatted
        assert "任务 2" in formatted
        assert "approve" in formatted or "审批" in formatted
    
    def test_map_task_to_table_heuristic(self, workflow):
        """Test heuristic keyword mapping for common tasks."""
        test_cases = [
            ("查询所有设备", ("device", "summarize")),
            ("检查接口状态", ("interfaces", "summarize")),
            ("BGP 会话健康", ("bgp", "summarize")),
            ("路由表分析", ("routes", "summarize")),
            ("OSPF 邻居关系", ("ospfIf", "summarize")),
        ]
        
        for task_text, expected in test_cases:
            result = workflow._map_task_to_table(task_text)
            if result:
                table, method, _ = result
                expected_table, expected_method = expected
                assert table == expected_table, f"Task '{task_text}' should map to table '{expected_table}'"
                assert method == expected_method

    @pytest.mark.asyncio
    async def test_hitl_interrupt_flag_on_uncertain_plan(self, workflow, initial_state):
        """Plan with uncertain tasks should set user_approval_required triggering HITL before execution."""
        # Build two todos: one maps cleanly (device), one no heuristic mapping (延迟异常)
        initial_state["todos"] = [
            TodoItem(id=1, task="查询设备", status="pending", result=None, deps=[], feasibility=None, recommended_table=None, schema_notes=None, evaluation_passed=None, evaluation_score=None, failure_reason=None),
            # Use LDP keyword (not in heuristic mapping list) to force uncertain classification
            TodoItem(id=2, task="检查 LDP 保留状态", status="pending", result=None, deps=[], feasibility=None, recommended_table=None, schema_notes=None, evaluation_passed=None, evaluation_score=None, failure_reason=None),
        ]
        device_schema = {"tables": ["device", "interfaces"], "device": {"fields": ["hostname"]}}
        latency_schema = {"tables": ["interfaces", "lldp"], "interfaces": {"fields": ["hostname", "ifname", "state"]}, "lldp": {"fields": ["hostname", "neighbor"]}}
        with patch("olav.tools.suzieq_parquet_tool.suzieq_schema_search") as mock_search:
            async def side_effect(args):
                q = args.get("query", "")
                if "设备" in q:
                    return device_schema
                if "LDP" in q or "Ldp" in q or "ldp" in q:
                    return latency_schema
                return {"tables": []}
            mock_search.ainvoke = AsyncMock(side_effect=side_effect)
            result = await workflow.schema_investigation_node(initial_state)
        plan = result["execution_plan"]
        assert plan is not None
        assert plan["user_approval_required"] is True
        assert len(plan["feasible_tasks"]) == 1
        assert len(plan["uncertain_tasks"]) == 1

    @pytest.mark.asyncio
    async def test_hitl_modify_plan_requires_reapproval(self, workflow, initial_state):
        """User modifying uncertain plan should still require approval until feasibility resolved."""
        initial_state["todos"] = [
            TodoItem(id=1, task="检查 LDP 配置", status="pending", result=None, deps=[], feasibility=None, recommended_table=None, schema_notes=None, evaluation_passed=None, evaluation_score=None, failure_reason=None),
        ]
        mock_schema = {"tables": ["lldp", "interfaces"], "lldp": {"fields": ["hostname", "neighbor"]}}
        with patch("olav.tools.suzieq_parquet_tool.suzieq_schema_search") as mock_search:
            mock_search.ainvoke = AsyncMock(return_value=mock_schema)
            result = await workflow.schema_investigation_node(initial_state)
        plan = result["execution_plan"]
        assert plan is not None and plan["user_approval_required"] is True
        # User overrides recommended table (simulated modification before approval)
        todo = result["todos"][0]
        assert todo["feasibility"] == "uncertain"
        todo["recommended_table"] = "interfaces"
        # Still pending approval (status unchanged)
        assert todo["status"] == "pending"


class TestDeepDiveRecursion:
    """Tests for implemented recursion logic (Phase 3.1)."""

    @pytest.fixture
    def workflow(self):
        with patch('olav.workflows.deep_dive.LLMFactory'):
            return DeepDiveWorkflow()

    @pytest.mark.asyncio
    async def test_recursive_check_triggers_on_failed_task(self, workflow):
        """Failed todo below max depth should trigger recursion and produce focused prompt."""
        state: DeepDiveState = {
            "messages": [HumanMessage(content="审计 BGP")],
            "todos": [
                TodoItem(
                    id=1,
                    task="检查 BGP 会话",
                    status="failed",
                    result="⚠️ 任务执行失败: NO_DATA_FOUND",
                    deps=[],
                    feasibility="feasible",
                    recommended_table="bgp",
                    schema_notes="✅", evaluation_passed=False,
                    evaluation_score=0.0, failure_reason="No data"
                )
            ],
            "execution_plan": None,
            "current_todo_id": 1,
            "completed_results": {1: "Failed"},
            "recursion_depth": 0,
            "max_depth": 3,
            "expert_mode": True,
            "trigger_recursion": False
        }
        result = await workflow.recursive_check_node(state)
        assert result.get("trigger_recursion") is True
        assert result.get("recursion_depth") == 1
        assert any(isinstance(m, HumanMessage) and "递归深入分析" in m.content for m in result.get("messages", []))
        # should_recurse decides next node; build merged state explicitly
        merged_state = state.copy()
        merged_state.update(result)
        next_node = await workflow.should_recurse(merged_state)
        assert next_node == "task_planning"

    @pytest.mark.asyncio
    async def test_recursive_check_stops_at_max_depth(self, workflow):
        """No recursion beyond max depth."""
        state: DeepDiveState = {
            "messages": [HumanMessage(content="test")],
            "todos": [
                TodoItem(
                    id=1, task="test", status="failed", result="fail", deps=[],
                    feasibility=None, recommended_table=None, schema_notes=None,
                    evaluation_passed=False, evaluation_score=0.0, failure_reason="test"
                )
            ],
            "execution_plan": None,
            "current_todo_id": 1,
            "completed_results": {1: "fail"},
            "recursion_depth": 3,
            "max_depth": 3,
            "expert_mode": True,
            "trigger_recursion": False
        }
        result = await workflow.recursive_check_node(state)
        assert result.get("trigger_recursion") is False
        assert any("Max recursion depth" in m.content for m in result.get("messages", []))
        next_node = await workflow.should_recurse(result | state)
        assert next_node == "final_summary"

    @pytest.mark.asyncio
    async def test_recursive_check_no_failed_tasks(self, workflow):
        """Completed todos without failures should not trigger recursion."""
        state: DeepDiveState = {
            "messages": [HumanMessage(content="审计 BGP")],
            "todos": [
                TodoItem(
                    id=1, task="检查 BGP 会话", status="completed", result="OK", deps=[],
                    feasibility="feasible", recommended_table="bgp", schema_notes="✅",
                    evaluation_passed=True, evaluation_score=1.0, failure_reason=None
                )
            ],
            "execution_plan": None,
            "current_todo_id": 1,
            "completed_results": {1: "OK"},
            "recursion_depth": 0,
            "max_depth": 3,
            "expert_mode": True,
            "trigger_recursion": False
        }
        result = await workflow.recursive_check_node(state)
        assert result.get("trigger_recursion") is False
        assert any("No deeper analysis" in m.content for m in result.get("messages", []))
        next_node = await workflow.should_recurse(result | state)
        assert next_node == "final_summary"

    @pytest.mark.asyncio
    async def test_should_recurse_switches_based_on_flag(self, workflow):
        """should_recurse returns task_planning only when trigger_recursion is True."""
        # Case 1: trigger_recursion True
        state_true: DeepDiveState = {
            "messages": [], "todos": [], "execution_plan": None,
            "current_todo_id": None, "completed_results": {},
            "recursion_depth": 1, "max_depth": 3, "expert_mode": True,
            "trigger_recursion": True
        }
        assert await workflow.should_recurse(state_true) == "task_planning"
        # Case 2: trigger_recursion False
        state_false = state_true.copy()
        state_false["trigger_recursion"] = False
        assert await workflow.should_recurse(state_false) == "final_summary"

    @pytest.mark.asyncio
    async def test_recursive_check_multi_failure_handling(self, workflow):
        """Multiple failed todos should all get sub-tasks (Phase 3.4 enhancement)."""
        state: DeepDiveState = {
            "messages": [HumanMessage(content="批量审计 BGP 和 OSPF")],
            "todos": [
                TodoItem(
                    id=1,
                    task="检查 BGP 会话",
                    status="failed",
                    result="⚠️ 任务执行失败: NO_DATA_FOUND - 表中无数据",
                    deps=[],
                    feasibility="feasible",
                    recommended_table="bgp",
                    schema_notes="✅",
                    evaluation_passed=False,
                    evaluation_score=0.0,
                    failure_reason="NO_DATA_FOUND"
                ),
                TodoItem(
                    id=2,
                    task="检查 OSPF 邻居",
                    status="failed",
                    result="⚠️ 任务执行失败: SCHEMA_NOT_FOUND - 未找到 ospf 表",
                    deps=[],
                    feasibility="uncertain",
                    recommended_table=None,
                    schema_notes="⚠️",
                    evaluation_passed=False,
                    evaluation_score=0.0,
                    failure_reason="SCHEMA_NOT_FOUND"
                ),
                TodoItem(
                    id=3,
                    task="检查接口状态",
                    status="completed",
                    result="✅ 成功: 发现 50 个接口",
                    deps=[],
                    feasibility="feasible",
                    recommended_table="interfaces",
                    schema_notes="✅",
                    evaluation_passed=True,
                    evaluation_score=1.0,
                    failure_reason=None
                ),
            ],
            "execution_plan": None,
            "current_todo_id": 2,
            "completed_results": {1: "Failed", 2: "Failed", 3: "OK"},
            "recursion_depth": 0,
            "max_depth": 3,
            "expert_mode": True,
            "trigger_recursion": False
        }
        
        result = await workflow.recursive_check_node(state)
        
        # Should trigger recursion
        assert result.get("trigger_recursion") is True
        assert result.get("recursion_depth") == 1
        
        # Message should reference BOTH failures (not just first one)
        messages = result.get("messages", [])
        assert len(messages) > 0
        recursive_prompt = next((m.content for m in messages if isinstance(m, HumanMessage)), "")
        
        # Verify both failed tasks are mentioned
        assert "失败任务 1" in recursive_prompt or "BGP" in recursive_prompt
        assert "失败任务 2" in recursive_prompt or "OSPF" in recursive_prompt
        
        # Verify prompt asks for multiple sub-tasks (not just one parent)
        assert "2 个失败任务" in recursive_prompt or "检测到 2 个" in recursive_prompt
        
        # Verify routing decision
        merged_state = state.copy()
        merged_state.update(result)
        next_node = await workflow.should_recurse(merged_state)
        assert next_node == "task_planning"

    @pytest.mark.asyncio
    async def test_recursive_check_limits_failures_processed(self, workflow):
        """If >3 failures exist, only top 3 should be analyzed to avoid prompt explosion."""
        state: DeepDiveState = {
            "messages": [HumanMessage(content="批量审计5个协议")],
            "todos": [
                TodoItem(
                    id=i,
                    task=f"检查协议 {i}",
                    status="failed",
                    result=f"失败: 协议 {i} 无数据",
                    deps=[],
                    feasibility="feasible",
                    recommended_table=f"protocol_{i}",
                    schema_notes="✅",
                    evaluation_passed=False,
                    evaluation_score=0.0,
                    failure_reason="NO_DATA_FOUND"
                )
                for i in range(1, 6)  # 5 failures
            ],
            "execution_plan": None,
            "current_todo_id": 5,
            "completed_results": {i: "Failed" for i in range(1, 6)},
            "recursion_depth": 0,
            "max_depth": 3,
            "expert_mode": True,
            "trigger_recursion": False
        }
        
        result = await workflow.recursive_check_node(state)
        
        # Should still trigger recursion
        assert result.get("trigger_recursion") is True
        
        # But prompt should only mention 3 failures (max_failures_per_recursion=3)
        messages = result.get("messages", [])
        recursive_prompt = next((m.content for m in messages if isinstance(m, HumanMessage)), "")
        
        # Should say "3 个失败任务" not "5 个"
        assert "3 个失败任务" in recursive_prompt or "检测到 3 个" in recursive_prompt
        assert "5 个" not in recursive_prompt


class TestDeepDiveParallel:
    """Tests for parallel batch execution logic (Phase 3.2)."""

    @pytest.fixture
    def workflow(self):
        with patch('olav.workflows.deep_dive.LLMFactory'):
            wf = DeepDiveWorkflow()
            # Provide dummy llm for fallback path (should not be used in main parallel success test)
            wf.llm = AsyncMock()
            return wf

    def _make_todo(self, id_: int, task: str, deps=None) -> TodoItem:
        if deps is None:
            deps = []
        return TodoItem(
            id=id_, task=task, status="pending", result=None, deps=deps,
            feasibility="feasible", recommended_table=None, schema_notes=None,
            evaluation_passed=None, evaluation_score=None, failure_reason=None
        )

    @pytest.mark.asyncio
    async def test_parallel_batch_exec_marks_multiple_completed(self, workflow):
        """Multiple independent todos should execute concurrently and mark completed."""
        state: DeepDiveState = {
            "messages": [HumanMessage(content="批量审计设备与接口与BGP")],
            "todos": [
                self._make_todo(1, "查询所有设备"),
                self._make_todo(2, "检查接口状态"),
                self._make_todo(3, "检查 BGP 会话"),
            ],
            "execution_plan": None,
            "current_todo_id": None,
            "completed_results": {},
            "recursion_depth": 0,
            "max_depth": 3,
            "expert_mode": True,
            "trigger_recursion": False,
            "parallel_batch_size": 5,
        }

        full_schema = {
            "tables": ["device", "interfaces", "bgp"],
            "device": {"fields": ["hostname", "version"]},
            "interfaces": {"fields": ["hostname", "ifname", "state"]},
            "bgp": {"fields": ["hostname", "peer", "state"]},
        }

        async def query_side_effect(args):
            table = args.get("table")
            return {
                "status": "OK",
                "table": table,
                "columns": ["hostname", "state"],
                "data": [{"hostname": "R1", "state": "up"}],
                "count": 1,
            }

        with patch("olav.tools.suzieq_parquet_tool.suzieq_schema_search") as mock_schema, \
             patch("olav.tools.suzieq_parquet_tool.suzieq_query") as mock_query, \
             patch("olav.evaluators.config_compliance.ConfigComplianceEvaluator") as mock_eval_cls:
            mock_schema.ainvoke = AsyncMock(return_value=full_schema)
            mock_query.ainvoke = AsyncMock(side_effect=query_side_effect)
            mock_eval = AsyncMock()
            mock_eval_result = MagicMock(passed=True, score=1.0, feedback="OK")
            mock_eval.evaluate = AsyncMock(return_value=mock_eval_result)
            mock_eval_cls.return_value = mock_eval

            result = await workflow.execute_todo_node(state)

        # All three should be completed via parallel path
        statuses = [t["status"] for t in result["todos"]]
        assert statuses.count("completed") == 3
        # Messages should include batch completion indicator
        assert any(isinstance(m, AIMessage) and "并行批次完成" in m.content for m in result["messages"])

    @pytest.mark.asyncio
    async def test_parallel_fallback_to_serial_when_single_ready(self, workflow):
        """If only one dependency-satisfied todo is ready, fallback serial path executes just one."""
        state: DeepDiveState = {
            "messages": [HumanMessage(content="审计单个设备然后接口")],
            "todos": [
                self._make_todo(1, "查询所有设备"),
                self._make_todo(2, "检查接口状态", deps=[1]),
            ],
            "execution_plan": None,
            "current_todo_id": None,
            "completed_results": {},
            "recursion_depth": 0,
            "max_depth": 3,
            "expert_mode": True,
            "trigger_recursion": False,
            "parallel_batch_size": 5,
        }
        schema = {"tables": ["device", "interfaces"], "device": {"fields": ["hostname"]}, "interfaces": {"fields": ["ifname"]}}
        with patch("olav.tools.suzieq_parquet_tool.suzieq_schema_search") as mock_schema, \
             patch("olav.tools.suzieq_parquet_tool.suzieq_query") as mock_query, \
             patch("olav.evaluators.config_compliance.ConfigComplianceEvaluator") as mock_eval_cls:
            mock_schema.ainvoke = AsyncMock(return_value=schema)
            mock_query.ainvoke = AsyncMock(return_value={
                "status": "OK", "table": "device", "columns": ["hostname"], "data": [{"hostname": "R1"}], "count": 1
            })
            mock_eval = AsyncMock()
            mock_eval_result = MagicMock(passed=True, score=1.0, feedback="OK")
            mock_eval.evaluate = AsyncMock(return_value=mock_eval_result)
            mock_eval_cls.return_value = mock_eval
            result = await workflow.execute_todo_node(state)
        # First completed, second still pending
        assert result["todos"][0]["status"] in {"completed"}
        assert result["todos"][1]["status"] == "pending"
        # No batch completion message (serial path)
        assert not any(isinstance(m, AIMessage) and "并行批次完成" in m.content for m in result["messages"])

        # Execute again to process second (now dependency satisfied)
        # Mock queries for interfaces
        with patch("olav.tools.suzieq_parquet_tool.suzieq_schema_search") as mock_schema, \
             patch("olav.tools.suzieq_parquet_tool.suzieq_query") as mock_query, \
             patch("olav.evaluators.config_compliance.ConfigComplianceEvaluator") as mock_eval_cls:
            mock_schema.ainvoke = AsyncMock(return_value=schema)
            mock_query.ainvoke = AsyncMock(return_value={
                "status": "OK", "table": "interfaces", "columns": ["hostname", "ifname"], "data": [{"hostname": "R1", "ifname": "xe-0/0/0"}], "count": 1
            })
            mock_eval = AsyncMock()
            mock_eval_result = MagicMock(passed=True, score=1.0, feedback="OK")
            mock_eval.evaluate = AsyncMock(return_value=mock_eval_result)
            mock_eval_cls.return_value = mock_eval
            state.update(result)  # merge updated todos
            result2 = await workflow.execute_todo_node(state)
        assert result2["todos"][1]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_parallel_batch_includes_failures_isolated(self, workflow):
        """Failure in one parallel task should not block others completing."""
        state: DeepDiveState = {
            "messages": [HumanMessage(content="批量执行设备与BGP")],
            "todos": [
                self._make_todo(1, "查询所有设备"),
                self._make_todo(2, "检查 BGP 会话"),
            ],
            "execution_plan": None,
            "current_todo_id": None,
            "completed_results": {},
            "recursion_depth": 0,
            "max_depth": 3,
            "expert_mode": True,
            "trigger_recursion": False,
            "parallel_batch_size": 5,
        }
        # Schema missing bgp table to induce failure
        partial_schema = {"tables": ["device", "interfaces"], "device": {"fields": ["hostname"]}}

        async def query_side_effect(args):
            table = args.get("table")
            return {
                "status": "OK",
                "table": table,
                "columns": ["hostname"],
                "data": [{"hostname": "R1"}],
                "count": 1,
            }
        with patch("olav.tools.suzieq_parquet_tool.suzieq_schema_search") as mock_schema, \
             patch("olav.tools.suzieq_parquet_tool.suzieq_query") as mock_query, \
             patch("olav.evaluators.config_compliance.ConfigComplianceEvaluator") as mock_eval_cls:
            mock_schema.ainvoke = AsyncMock(return_value=partial_schema)
            mock_query.ainvoke = AsyncMock(side_effect=query_side_effect)
            mock_eval = AsyncMock()
            mock_eval_result = MagicMock(passed=True, score=1.0, feedback="OK")
            mock_eval.evaluate = AsyncMock(return_value=mock_eval_result)
            mock_eval_cls.return_value = mock_eval
            result = await workflow.execute_todo_node(state)
        # Device should succeed, BGP should fail due to SCHEMA_NOT_FOUND
        todo_map = {t["id"]: t for t in result["todos"]}
        assert todo_map[1]["status"] == "completed"
        assert todo_map[2]["status"] == "failed"
        assert any("SCHEMA_NOT_FOUND" in (todo_map[2]["result"] or "") for _ in [0])
        assert any(isinstance(m, AIMessage) and "并行批次完成" in m.content for m in result["messages"])

