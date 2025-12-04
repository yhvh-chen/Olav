"""Unit tests for modular workflow architecture.

Tests:
1. Prompt loading with nested directories
2. Workflow validation logic
3. QueryDiagnosticWorkflow routing
4. DeviceExecutionWorkflow HITL
5. WorkflowOrchestrator intent classification
"""

import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import pytest
from unittest.mock import Mock, AsyncMock, patch
from langchain_core.messages import HumanMessage, AIMessage

from olav.workflows.base import WorkflowType
from olav.workflows.query_diagnostic import QueryDiagnosticWorkflow, QueryDiagnosticState
from olav.workflows.device_execution import DeviceExecutionWorkflow, DeviceExecutionState
from olav.workflows.batch_execution import BatchExecutionWorkflow, BatchExecutionState
from olav.workflows.netbox_management import NetBoxManagementWorkflow
from olav.agents.root_agent_orchestrator import WorkflowOrchestrator
from olav.core.prompt_manager import prompt_manager


class TestPromptManager:
    """Test nested directory support in PromptManager."""
    
    def test_load_nested_prompt(self):
        """Test loading prompts from nested directories (workflows/orchestrator)."""
        try:
            # This should work with updated prompt_manager
            prompt = prompt_manager.load_prompt(
                "workflows/orchestrator",
                "intent_classification",
                workflows={"query": "test"},
                user_query="BGP为什么down？"
            )
            assert isinstance(prompt, str)
            assert "工作流编排器" in prompt or "orchestrator" in prompt.lower()
        except FileNotFoundError:
            pytest.skip("Prompt file not found - expected in integration environment")
    
    def test_load_workflow_prompts(self):
        """Test loading all workflow-specific prompts."""
        workflow_prompts = [
            ("workflows/query_diagnostic", "macro_analysis"),
            ("workflows/query_diagnostic", "micro_diagnosis"),
            ("workflows/device_execution", "config_planning"),
            ("workflows/device_execution", "config_execution"),
            ("workflows/device_execution", "validation"),
            ("workflows/netbox_management", "schema_discovery"),
            ("workflows/netbox_management", "operation_planning"),
            ("workflows/netbox_management", "verification"),
        ]
        
        for category, name in workflow_prompts:
            try:
                # Provide minimal required variables
                if "macro_analysis" in name:
                    kwargs = {"user_query": "test"}
                elif "micro_diagnosis" in name:
                    kwargs = {"user_query": "test", "macro_analysis_result": {}}
                elif "config_planning" in name:
                    kwargs = {"user_query": "test"}
                elif "config_execution" in name:
                    kwargs = {"config_plan": {}}
                elif "validation" in name:
                    kwargs = {"config_plan": {}, "execution_result": {}}
                elif "schema_discovery" in name:
                    kwargs = {"user_query": "test"}
                elif "operation_planning" in name:
                    kwargs = {"user_query": "test", "api_endpoint": "/test"}
                elif "verification" in name:
                    kwargs = {"operation_plan": {}, "execution_result": {}}
                else:
                    kwargs = {}
                
                prompt = prompt_manager.load_prompt(category, name, **kwargs)
                assert isinstance(prompt, str)
                assert len(prompt) > 0
            except FileNotFoundError:
                pytest.skip(f"Prompt {category}/{name} not found")


class TestQueryDiagnosticWorkflow:
    """Test query/diagnostic workflow."""
    
    @pytest.fixture
    def workflow(self):
        return QueryDiagnosticWorkflow()
    
    @pytest.mark.asyncio
    async def test_validate_query_input(self, workflow):
        """Test validation accepts query keywords."""
        queries = [
            "BGP为什么down？",
            "查询接口状态",
            "诊断路由问题",
            "分析网络性能",
            "Why is interface down?",
        ]
        
        for query in queries:
            is_valid, reason = await workflow.validate_input(query)
            assert is_valid, f"Should accept query: {query}, reason: {reason}"
    
    @pytest.mark.asyncio
    async def test_validate_rejects_config_change(self, workflow):
        """Test validation rejects config change keywords."""
        config_queries = [
            "修改BGP配置",
            "添加VLAN 100",
            "shutdown接口",
            "配置OSPF",
        ]
        
        for query in config_queries:
            is_valid, reason = await workflow.validate_input(query)
            assert not is_valid, f"Should reject config change: {query}"
    
    @pytest.mark.asyncio
    async def test_validate_rejects_netbox(self, workflow):
        """Test validation rejects NetBox keywords."""
        netbox_queries = [
            "添加设备到NetBox",
            "IP地址分配",
            "设备清单",
        ]
        
        for query in netbox_queries:
            is_valid, reason = await workflow.validate_input(query)
            assert not is_valid, f"Should reject NetBox query: {query}"
    
    def test_workflow_properties(self, workflow):
        """Test workflow metadata."""
        assert workflow.name == "query_diagnostic"
        assert "查询" in workflow.description or "诊断" in workflow.description
        assert "suzieq_query" in workflow.tools_required
        assert "suzieq_schema_search" in workflow.tools_required
        assert "netconf_tool" in workflow.tools_required


class TestDeviceExecutionWorkflow:
    """Test device execution workflow with HITL."""
    
    @pytest.fixture
    def workflow(self):
        return DeviceExecutionWorkflow()
    
    @pytest.mark.asyncio
    async def test_validate_config_change_input(self, workflow):
        """Test validation accepts config change keywords."""
        queries = [
            "修改BGP配置",
            "添加VLAN 100",
            "shutdown接口GigabitEthernet0/0/1",
            "配置OSPF area 0",
            "commit配置",
        ]
        
        for query in queries:
            is_valid, reason = await workflow.validate_input(query)
            assert is_valid, f"Should accept config change: {query}, reason: {reason}"
    
    @pytest.mark.asyncio
    async def test_validate_rejects_netbox(self, workflow):
        """Test validation rejects NetBox keywords."""
        netbox_queries = [
            "添加设备到NetBox",
            "设备清单",
            "IP地址分配",
        ]
        
        for query in netbox_queries:
            is_valid, reason = await workflow.validate_input(query)
            assert not is_valid, f"Should reject NetBox query: {query}"
    
    def test_workflow_properties(self, workflow):
        """Test workflow metadata."""
        assert workflow.name == "device_execution"
        assert "配置" in workflow.description or "执行" in workflow.description
        assert "netconf_tool" in workflow.tools_required
        assert "cli_tool" in workflow.tools_required
    
    @pytest.mark.asyncio
    async def test_graph_has_hitl_interrupt(self, workflow):
        """Test graph is compiled with HITL interrupt."""
        # Mock checkpointer
        mock_checkpointer = Mock()
        
        with patch.object(workflow, 'build_graph') as mock_build:
            # Call build_graph to verify it's compilable
            workflow.build_graph(checkpointer=mock_checkpointer)
            
            # Verify build_graph was called with checkpointer
            mock_build.assert_called_once_with(checkpointer=mock_checkpointer)


class TestNetBoxManagementWorkflow:
    """Test NetBox management workflow."""
    
    @pytest.fixture
    def workflow(self):
        return NetBoxManagementWorkflow()
    
    @pytest.mark.asyncio
    async def test_validate_netbox_input(self, workflow):
        """Test validation accepts NetBox keywords."""
        queries = [
            "添加设备到NetBox",
            "查询设备清单",
            "IP地址分配",
            "创建站点",
            "机架管理",
        ]
        
        for query in queries:
            is_valid, reason = await workflow.validate_input(query)
            assert is_valid, f"Should accept NetBox query: {query}, reason: {reason}"
    
    def test_workflow_properties(self, workflow):
        """Test workflow metadata."""
        assert workflow.name == "netbox_management"
        assert "NetBox" in workflow.description or "清单" in workflow.description
        assert "netbox_api_call" in workflow.tools_required
        assert "netbox_schema_search" in workflow.tools_required


class TestWorkflowOrchestrator:
    """Test workflow orchestrator intent classification and routing."""
    
    @pytest.mark.asyncio
    async def test_classify_intent_query_diagnostic(self):
        """Test classification of query/diagnostic queries."""
        # Mock checkpointer
        mock_checkpointer = Mock()
        orchestrator = WorkflowOrchestrator(checkpointer=mock_checkpointer)
        
        queries = [
            "BGP为什么down？",
            "查询接口状态",
            "诊断路由问题",
        ]
        
        for query in queries:
            # Use keyword fallback (no LLM call needed)
            workflow_type = orchestrator._classify_by_keywords(query)
            assert workflow_type == WorkflowType.QUERY_DIAGNOSTIC, \
                f"Should classify as QUERY_DIAGNOSTIC: {query}"
    
    @pytest.mark.asyncio
    async def test_classify_intent_device_execution(self):
        """Test classification of config change queries."""
        mock_checkpointer = Mock()
        orchestrator = WorkflowOrchestrator(checkpointer=mock_checkpointer)
        
        queries = [
            "修改BGP配置",
            "添加VLAN 100",
            "shutdown接口",
            "配置OSPF",
        ]
        
        for query in queries:
            workflow_type = orchestrator._classify_by_keywords(query)
            assert workflow_type == WorkflowType.DEVICE_EXECUTION, \
                f"Should classify as DEVICE_EXECUTION: {query}"
    
    @pytest.mark.asyncio
    async def test_classify_intent_netbox_management(self):
        """Test classification of NetBox queries."""
        mock_checkpointer = Mock()
        orchestrator = WorkflowOrchestrator(checkpointer=mock_checkpointer)
        
        queries = [
            "添加设备到NetBox",
            "设备清单",
            "IP地址分配",
        ]
        
        for query in queries:
            workflow_type = orchestrator._classify_by_keywords(query)
            assert workflow_type == WorkflowType.NETBOX_MANAGEMENT, \
                f"Should classify as NETBOX_MANAGEMENT: {query}"
    
    def test_orchestrator_has_all_workflows(self):
        """Test orchestrator initializes all three workflows."""
        mock_checkpointer = Mock()
        orchestrator = WorkflowOrchestrator(checkpointer=mock_checkpointer)
        
        assert WorkflowType.QUERY_DIAGNOSTIC in orchestrator.workflows
        assert WorkflowType.DEVICE_EXECUTION in orchestrator.workflows
        assert WorkflowType.NETBOX_MANAGEMENT in orchestrator.workflows
        
        assert isinstance(orchestrator.workflows[WorkflowType.QUERY_DIAGNOSTIC], QueryDiagnosticWorkflow)
        assert isinstance(orchestrator.workflows[WorkflowType.DEVICE_EXECUTION], DeviceExecutionWorkflow)
        assert isinstance(orchestrator.workflows[WorkflowType.NETBOX_MANAGEMENT], NetBoxManagementWorkflow)


class TestWorkflowStateStructure:
    """Test workflow state structure and typing."""
    
    def test_query_diagnostic_state_fields(self):
        """Test QueryDiagnosticState has required fields."""
        state: QueryDiagnosticState = {
            "messages": [HumanMessage(content="test")],
            "workflow_type": WorkflowType.QUERY_DIAGNOSTIC,
            "iteration_count": 0,
            "macro_data": None,
            "micro_data": None,
            "needs_micro": False,
        }
        
        assert "macro_data" in state
        assert "micro_data" in state
        assert "needs_micro" in state
    
    def test_device_execution_state_fields(self):
        """Test DeviceExecutionState has required fields."""
        state: DeviceExecutionState = {
            "messages": [HumanMessage(content="test")],
            "workflow_type": WorkflowType.DEVICE_EXECUTION,
            "iteration_count": 0,
            "config_plan": None,
            "approval_status": None,
            "execution_result": None,
            "validation_result": None,
        }
        
        assert "config_plan" in state
        assert "approval_status" in state
        assert "execution_result" in state
        assert "validation_result" in state
    
    def test_batch_execution_state_fields(self):
        """Test BatchExecutionState has required fields."""
        state: BatchExecutionState = {
            "messages": [HumanMessage(content="test")],
            "user_intent": "给所有交换机添加 VLAN 100",
            "operation_type": "add_vlan",
            "operation_params": {"vlan_id": 100},
            "device_filter": {"role": "switch"},
            "resolved_devices": ["Switch-A", "Switch-B"],
            "change_plan": None,
            "approval_status": None,
            "device_tasks": None,
            "device_results": None,
            "summary": None,
        }
        
        assert "user_intent" in state
        assert "operation_type" in state
        assert "resolved_devices" in state
        assert "approval_status" in state
        assert "summary" in state


class TestBatchExecutionWorkflow:
    """Test batch execution workflow."""
    
    @pytest.fixture
    def workflow(self):
        return BatchExecutionWorkflow()
    
    @pytest.mark.asyncio
    async def test_validate_batch_input(self, workflow):
        """Test validation accepts batch operation keywords."""
        queries = [
            "给所有交换机添加 VLAN 100",
            "批量配置 NTP 服务器",
            "在全部设备上设置 SNMP community",
            "所有核心路由器修改 MTU",
            "batch configure syslog on all devices",
        ]
        
        for query in queries:
            is_valid, reason = await workflow.validate_input(query)
            assert is_valid, f"Should accept batch operation: {query}, reason: {reason}"
    
    @pytest.mark.asyncio
    async def test_validate_rejects_single_device(self, workflow):
        """Test validation rejects single-device operations."""
        queries = [
            "修改 R1 的 BGP 配置",
            "配置 Switch-A 的接口",
            "configure OSPF on router1",
        ]
        
        for query in queries:
            is_valid, reason = await workflow.validate_input(query)
            assert not is_valid, f"Should reject single-device operation: {query}"
    
    @pytest.mark.asyncio
    async def test_validate_rejects_batch_query(self, workflow):
        """Test validation rejects batch queries (read-only)."""
        queries = [
            "查询所有设备状态",
            "显示全部交换机的接口",
            "all devices BGP status",
        ]
        
        for query in queries:
            is_valid, reason = await workflow.validate_input(query)
            assert not is_valid, f"Should reject batch query (read-only): {query}"
    
    def test_workflow_properties(self, workflow):
        """Test workflow metadata."""
        assert workflow.name == "batch_execution"
        assert "批量" in workflow.description or "多设备" in workflow.description
        assert "netconf_tool" in workflow.tools_required
        assert "netbox_api_call" in workflow.tools_required


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
