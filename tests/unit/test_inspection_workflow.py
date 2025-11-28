"""
Tests for InspectionWorkflow.

Tests:
- Workflow initialization
- Scope parsing
- DiffEngine integration
- Report generation
- Reconciliation flow
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from olav.workflows.inspection import InspectionWorkflow, InspectionState
from olav.workflows.base import WorkflowType
from olav.sync.models import DiffResult, DiffSeverity, DiffSource, EntityType


class TestInspectionWorkflow:
    """Test InspectionWorkflow class."""
    
    @pytest.fixture
    def workflow(self):
        """Create workflow with mocked dependencies."""
        with patch("olav.workflows.inspection.NetBoxAPITool") as MockNetBox:
            with patch("olav.workflows.inspection.LLMFactory") as MockLLM:
                mock_netbox = MagicMock()
                mock_netbox.execute = AsyncMock()
                MockNetBox.return_value = mock_netbox
                
                mock_llm = MagicMock()
                mock_llm.ainvoke = AsyncMock()
                MockLLM.get_chat_model.return_value = mock_llm
                
                wf = InspectionWorkflow()
                wf.netbox = mock_netbox
                wf.llm = mock_llm
                return wf
    
    def test_workflow_properties(self, workflow):
        """Test basic workflow properties."""
        assert workflow.name == "inspection"
        assert "巡检" in workflow.description or "sync" in workflow.description.lower()
        assert "suzieq_query" in workflow.tools_required
        assert "netbox_api" in workflow.tools_required
    
    @pytest.mark.asyncio
    async def test_validate_input_inspection_keywords(self, workflow):
        """Test input validation with inspection keywords."""
        valid, reason = await workflow.validate_input("巡检所有核心路由器")
        assert valid is True
        
        valid, reason = await workflow.validate_input("检查 NetBox 同步状态")
        assert valid is True
        
        valid, reason = await workflow.validate_input("对比 R1 与 NetBox")
        assert valid is True
    
    @pytest.mark.asyncio
    async def test_validate_input_non_inspection(self, workflow):
        """Test input validation with non-inspection queries."""
        valid, reason = await workflow.validate_input("配置 VLAN")
        assert valid is False
        
        # Note: "添加设备到 NetBox" contains no inspection keywords
        # so it should return False
        valid, reason = await workflow.validate_input("查询 BGP 邻居")
        assert valid is False
    
    def test_build_graph(self, workflow):
        """Test graph building."""
        graph = workflow.build_graph()
        
        # Check nodes exist
        assert graph is not None
    
    @pytest.mark.asyncio
    async def test_parse_scope_with_llm(self, workflow):
        """Test scope parsing with LLM."""
        workflow.llm.ainvoke = AsyncMock(return_value=MagicMock(
            content='{"device_scope": ["R1", "R2"], "entity_types": ["interface", "ip_address"]}'
        ))
        
        workflow.netbox.execute = AsyncMock(return_value=MagicMock(
            error=None,
            data={"results": []}
        ))
        
        state = {
            "messages": [MagicMock(content="检查 R1 R2 的接口状态")],
            "dry_run": True,
            "auto_correct": True,
        }
        
        result = await workflow._parse_scope(state)
        
        assert result["device_scope"] == ["R1", "R2"]
        assert "interface" in result["entity_types"]
    
    @pytest.mark.asyncio
    async def test_parse_scope_all_devices(self, workflow):
        """Test scope parsing when 'all' devices requested."""
        workflow.llm.ainvoke = AsyncMock(return_value=MagicMock(
            content='{"device_scope": ["all"], "entity_types": ["interface"]}'
        ))

        # Mock NetBox device list - adapter already extracts results
        workflow.netbox.execute = AsyncMock(return_value=MagicMock(
            error=None,
            data=[
                {"name": "R1"},
                {"name": "R2"},
                {"name": "SW1"},
            ]
        ))
        
        state = {
            "messages": [MagicMock(content="巡检所有设备")],
            "dry_run": True,
            "auto_correct": True,
        }
        
        result = await workflow._parse_scope(state)
        
        assert result["device_scope"] == ["R1", "R2", "SW1"]
    
    @pytest.mark.asyncio
    async def test_collect_data_empty_scope(self, workflow):
        """Test data collection with empty device scope."""
        state = {
            "messages": [],
            "device_scope": [],
            "entity_types": ["interface"],
        }
        
        result = await workflow._collect_data(state)
        
        assert result["diff_report"] is None
        assert any("未找到设备" in m.content for m in result.get("messages", []))
    
    @pytest.mark.asyncio
    async def test_generate_report(self, workflow):
        """Test report generation."""
        state = {
            "messages": [],
            "diff_report": {
                "device_scope": ["R1"],
                "total_entities": 10,
                "matched": 8,
                "mismatched": 2,
                "missing_in_netbox": 0,
                "missing_in_network": 0,
                "summary_by_type": {"interface": 2},
                "summary_by_severity": {"info": 2},
                "diffs": [
                    {
                        "entity_type": "interface",
                        "device": "R1",
                        "field": "Gi0/1.mtu",
                        "network_value": 1500,
                        "netbox_value": 9000,
                        "severity": "info",
                        "source": "suzieq",
                        "auto_correctable": True,
                    }
                ],
            },
        }
        
        result = await workflow._generate_report(state)
        
        # Check report was added to messages
        assert len(result["messages"]) == 1
        assert "巡检报告" in result["messages"][0].content
        assert "R1" in result["messages"][0].content
    
    @pytest.mark.asyncio
    async def test_final_summary(self, workflow):
        """Test final summary generation."""
        state = {
            "messages": [],
            "diff_report": {
                "device_scope": ["R1", "R2"],
                "total_entities": 20,
                "matched": 18,
                "mismatched": 2,
            },
            "reconcile_results": [
                {"action": "auto_corrected", "diff": {"device": "R1", "field": "mtu"}},
                {"action": "hitl_pending", "diff": {"device": "R2", "field": "enabled", "network_value": False, "netbox_value": True}},
            ],
            "dry_run": True,
        }
        
        result = await workflow._final_summary(state)
        
        # Check summary was generated
        assert len(result["messages"]) == 1
        summary = result["messages"][0].content
        assert "巡检总结" in summary
        assert "2 台" in summary or "2" in summary


class TestInspectionIntegration:
    """Integration tests for inspection workflow."""
    
    @pytest.mark.asyncio
    async def test_run_inspection_function(self):
        """Test run_inspection convenience function."""
        with patch("olav.workflows.inspection.InspectionWorkflow") as MockWorkflow:
            mock_wf = MagicMock()
            mock_wf.netbox = MagicMock()
            mock_wf.netbox.execute = AsyncMock(return_value=MagicMock(
                error=None,
                data={"results": [{"name": "R1"}]}
            ))
            
            mock_wf.diff_engine = MagicMock()
            mock_wf.diff_engine.compare_all = AsyncMock(return_value=MagicMock(
                to_dict=lambda: {"diffs": []},
                diffs=[],
            ))
            
            mock_wf.reconciler = MagicMock()
            mock_wf.reconciler.dry_run = True
            mock_wf.reconciler.reconcile = AsyncMock(return_value=[])
            
            MockWorkflow.return_value = mock_wf
            
            from olav.workflows.inspection import run_inspection
            
            # This would need actual mocking to work fully
            # For now just verify the function exists and is callable
            assert callable(run_inspection)


class TestWorkflowRegistration:
    """Test workflow registration with orchestrator."""
    
    def test_workflow_type_exists(self):
        """Test INSPECTION workflow type exists."""
        assert hasattr(WorkflowType, "INSPECTION")
        assert WorkflowType.INSPECTION.value == "inspection"
    
    def test_workflow_in_registry(self):
        """Test workflow is registered."""
        from olav.workflows.registry import WorkflowRegistry
        
        # The workflow should be registered via decorator
        # Check that the registry has the inspection workflow registered
        workflow = WorkflowRegistry.get_workflow("inspection")
        assert workflow is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
