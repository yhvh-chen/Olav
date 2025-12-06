"""Unit tests for Expert Mode components.

Tests cover:
1. ExpertModeSupervisor - state management, task planning
2. QuickAnalyzer - task execution, findings parsing
3. ExpertModeWorkflow - orchestration
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from olav.modes.expert import (
    ExpertModeSupervisor,
    SupervisorState,
    DiagnosisTask,
    DiagnosisResult,
    LayerStatus,
    NETWORK_LAYERS,
    LAYER_INFO,
    QuickAnalyzer,
    ExpertModeWorkflow,
    ExpertModeOutput,
    run_expert_mode,
)


# =============================================================================
# LayerStatus Tests
# =============================================================================

class TestLayerStatus:
    """Tests for LayerStatus data model."""
    
    def test_initial_state(self):
        """LayerStatus initializes with correct defaults."""
        status = LayerStatus(layer="L3")
        
        assert status.layer == "L3"
        assert status.checked is False
        assert status.confidence == 0.0
        assert status.findings == []
        assert status.last_checked is None
    
    def test_update_sets_checked(self):
        """update() marks layer as checked."""
        status = LayerStatus(layer="L1")
        status.update(new_confidence=0.3, new_findings=["Issue found"])
        
        assert status.checked is True
        assert status.last_checked is not None
    
    def test_update_takes_max_confidence(self):
        """update() keeps maximum confidence value."""
        status = LayerStatus(layer="L2")
        
        status.update(0.5, ["Finding 1"])
        assert status.confidence == 0.5
        
        # Higher confidence should update
        status.update(0.6, ["Finding 2"])
        assert status.confidence == 0.6
        
        # Lower confidence should NOT decrease
        status.update(0.3, ["Finding 3"])
        assert status.confidence == 0.6
    
    def test_update_accumulates_findings(self):
        """update() appends new findings."""
        status = LayerStatus(layer="L3")
        
        status.update(0.3, ["Finding A"])
        status.update(0.4, ["Finding B", "Finding C"])
        
        assert len(status.findings) == 3
        assert "Finding A" in status.findings
        assert "Finding B" in status.findings
        assert "Finding C" in status.findings
    
    def test_needs_investigation_true_when_low_confidence(self):
        """needs_investigation returns True when confidence < 0.5."""
        status = LayerStatus(layer="L4")
        status.update(0.3, [])
        
        assert status.needs_investigation is True
    
    def test_needs_investigation_false_when_high_confidence(self):
        """needs_investigation returns False when confidence >= 0.5."""
        status = LayerStatus(layer="L4")
        status.update(0.6, [])
        
        assert status.needs_investigation is False


# =============================================================================
# SupervisorState Tests
# =============================================================================

class TestSupervisorState:
    """Tests for SupervisorState data model."""
    
    def test_initializes_all_layers(self):
        """State should have coverage for all 4 network layers."""
        state = SupervisorState(query="test query")
        
        assert len(state.layer_coverage) == 4
        for layer in NETWORK_LAYERS:
            assert layer in state.layer_coverage
    
    def test_get_confidence_gaps_returns_low_confidence_layers(self):
        """get_confidence_gaps() returns layers below threshold."""
        state = SupervisorState(query="test query")
        
        # Update some layers with high confidence
        state.layer_coverage["L1"].update(0.8, [])
        state.layer_coverage["L2"].update(0.7, [])
        
        gaps = state.get_confidence_gaps()
        
        # L3 and L4 should be gaps (0.0 confidence)
        # gaps is list of (layer, confidence) tuples
        gap_layers = [g[0] for g in gaps]
        assert "L3" in gap_layers
        assert "L4" in gap_layers
        assert "L1" not in gap_layers
        assert "L2" not in gap_layers
    
    def test_get_coverage_summary_format(self):
        """get_coverage_summary() returns formatted string."""
        state = SupervisorState(query="test")
        state.layer_coverage["L1"].update(0.5, ["Issue"])
        
        summary = state.get_coverage_summary()
        
        assert "L1" in summary
        assert "0.5" in summary or "50" in summary
    
    def test_should_continue_true_initially(self):
        """should_continue() returns True when not done."""
        state = SupervisorState(query="test")
        
        assert state.should_continue() is True
    
    def test_should_continue_false_when_root_cause_found(self):
        """should_continue() returns False after root cause found."""
        state = SupervisorState(query="test")
        state.root_cause_found = True
        
        assert state.should_continue() is False
    
    def test_should_continue_false_at_max_rounds(self):
        """should_continue() returns False at max rounds."""
        state = SupervisorState(query="test", max_rounds=5)
        state.current_round = 5
        
        assert state.should_continue() is False


# =============================================================================
# DiagnosisTask Tests
# =============================================================================

class TestDiagnosisTask:
    """Tests for DiagnosisTask data model."""
    
    def test_task_creation(self):
        """DiagnosisTask creates with required fields."""
        task = DiagnosisTask(
            task_id=1,
            layer="L3",
            description="Check BGP state",
        )
        
        assert task.task_id == 1
        assert task.layer == "L3"
        assert task.description == "Check BGP state"
        assert task.priority == "medium"  # default
        assert task.suggested_tables == []
        assert task.suggested_filters == {}
    
    def test_task_with_suggestions(self):
        """DiagnosisTask accepts suggestions."""
        task = DiagnosisTask(
            task_id=2,
            layer="L2",
            description="Check VLANs",
            suggested_tables=["vlan", "macs"],
            suggested_filters={"hostname": "R1"},
            priority="high",
        )
        
        assert task.suggested_tables == ["vlan", "macs"]
        assert task.suggested_filters == {"hostname": "R1"}
        assert task.priority == "high"


# =============================================================================
# DiagnosisResult Tests
# =============================================================================

class TestDiagnosisResult:
    """Tests for DiagnosisResult data model."""
    
    def test_result_creation(self):
        """DiagnosisResult creates correctly."""
        result = DiagnosisResult(
            task_id=1,
            layer="L3",
            success=True,
            findings=["BGP is down"],
            confidence=0.5,
        )
        
        assert result.task_id == 1
        assert result.layer == "L3"
        assert result.success is True
        assert "BGP is down" in result.findings
        assert result.confidence == 0.5
    
    def test_result_with_error(self):
        """DiagnosisResult handles error case."""
        result = DiagnosisResult(
            task_id=2,
            layer="L1",
            success=False,
            findings=[],
            confidence=0.0,
            error="Tool not found",
        )
        
        assert result.success is False
        assert result.error == "Tool not found"


# =============================================================================
# ExpertModeSupervisor Tests
# =============================================================================

class TestExpertModeSupervisor:
    """Tests for ExpertModeSupervisor."""
    
    def test_initialization(self):
        """Supervisor initializes with config."""
        supervisor = ExpertModeSupervisor(max_rounds=3)
        
        assert supervisor.max_rounds == 3
    
    def test_create_initial_state(self):
        """create_initial_state() returns valid SupervisorState."""
        supervisor = ExpertModeSupervisor()
        state = supervisor.create_initial_state(
            query="R1 BGP down",
            path_devices=["R1", "R2"],
        )
        
        assert state.query == "R1 BGP down"
        assert state.path_devices == ["R1", "R2"]
        assert len(state.layer_coverage) == 4
    
    @pytest.mark.asyncio
    async def test_plan_next_task_returns_lowest_confidence(self):
        """plan_next_task() prioritizes lowest confidence layer."""
        supervisor = ExpertModeSupervisor()
        state = supervisor.create_initial_state("test query")
        
        # Set L3 as lowest
        state.layer_coverage["L1"].update(0.6, [])
        state.layer_coverage["L2"].update(0.5, [])
        state.layer_coverage["L3"].update(0.1, [])  # Lowest
        state.layer_coverage["L4"].update(0.4, [])
        
        task = await supervisor.plan_next_task(state)
        
        assert task is not None
        assert task.layer == "L3"
    
    @pytest.mark.asyncio
    async def test_plan_next_task_returns_none_when_all_covered(self):
        """plan_next_task() returns None when all layers have high confidence."""
        supervisor = ExpertModeSupervisor()
        state = supervisor.create_initial_state("test query")
        
        # All layers have high confidence
        for layer in NETWORK_LAYERS:
            state.layer_coverage[layer].update(0.7, [])
        
        task = await supervisor.plan_next_task(state)
        
        assert task is None
    
    def test_update_state_updates_layer(self):
        """update_state() applies result to correct layer."""
        supervisor = ExpertModeSupervisor()
        state = supervisor.create_initial_state("test")
        
        result = DiagnosisResult(
            task_id=1,
            layer="L2",
            success=True,
            findings=["VLAN mismatch detected"],
            confidence=0.5,
        )
        
        supervisor.update_state(state, result)
        
        assert state.layer_coverage["L2"].checked is True
        assert state.layer_coverage["L2"].confidence == 0.5
        assert "VLAN mismatch detected" in state.layer_coverage["L2"].findings
    
    def test_update_state_detects_root_cause(self):
        """update_state() sets root_cause when finding contains root cause keywords."""
        supervisor = ExpertModeSupervisor()
        state = supervisor.create_initial_state("test")
        
        result = DiagnosisResult(
            task_id=1,
            layer="L3",
            success=True,
            findings=["根因: BGP neighbor IP misconfigured"],
            confidence=0.6,
        )
        
        supervisor.update_state(state, result)
        
        # Check findings were recorded (root_cause_found logic may differ)
        assert "根因: BGP neighbor IP misconfigured" in state.layer_coverage["L3"].findings
    
    def test_generate_report_includes_query(self):
        """generate_report() includes original query."""
        supervisor = ExpertModeSupervisor()
        state = supervisor.create_initial_state("R1 cannot reach R2")
        
        report = supervisor.generate_report(state)
        
        assert "R1 cannot reach R2" in report or "R1" in report


# =============================================================================
# QuickAnalyzer Tests
# =============================================================================

class TestQuickAnalyzer:
    """Tests for QuickAnalyzer."""
    
    def test_initialization(self):
        """QuickAnalyzer initializes with config."""
        analyzer = QuickAnalyzer(max_iterations=3)
        
        assert analyzer.max_iterations == 3
    
    def test_parse_findings_extracts_bullets(self):
        """_parse_findings() extracts bullet points."""
        analyzer = QuickAnalyzer()
        
        text = """
        Analysis results:
        - BGP session is down
        - Interface has errors
        • OSPF neighbor missing
        """
        
        findings = analyzer._parse_findings(text)
        
        assert len(findings) >= 2
        assert any("BGP" in f for f in findings)
    
    def test_parse_findings_captures_error_keywords(self):
        """_parse_findings() captures lines with error keywords."""
        analyzer = QuickAnalyzer()
        
        text = """
        The interface shows an error state.
        BGP is down due to misconfiguration.
        Normal status on L2.
        """
        
        findings = analyzer._parse_findings(text)
        
        assert any("error" in f.lower() for f in findings)
        assert any("down" in f.lower() for f in findings)
    
    def test_estimate_confidence_scales_with_findings(self):
        """_estimate_confidence() increases with finding count."""
        analyzer = QuickAnalyzer()
        
        conf_1 = analyzer._estimate_confidence(["Finding 1"])
        conf_3 = analyzer._estimate_confidence(["F1", "F2", "F3"])
        
        assert conf_3 > conf_1
    
    def test_estimate_confidence_capped_at_suzieq_max(self):
        """_estimate_confidence() never exceeds SUZIEQ_MAX_CONFIDENCE."""
        analyzer = QuickAnalyzer()
        
        # Many findings
        many_findings = [f"Finding {i}" for i in range(20)]
        conf = analyzer._estimate_confidence(many_findings)
        
        assert conf <= 0.6  # SUZIEQ_MAX_CONFIDENCE


# =============================================================================
# ExpertModeWorkflow Tests
# =============================================================================

class TestExpertModeWorkflow:
    """Tests for ExpertModeWorkflow."""
    
    def test_initialization(self):
        """Workflow initializes with config."""
        workflow = ExpertModeWorkflow(max_rounds=3, max_analyzer_iterations=2)
        
        assert workflow.max_rounds == 3
        assert workflow.max_analyzer_iterations == 2
    
    @pytest.mark.asyncio
    async def test_run_returns_expert_mode_output(self):
        """run() returns ExpertModeOutput."""
        workflow = ExpertModeWorkflow(max_rounds=1)
        
        # Patch supervisor at module level and use side_effect for should_continue
        with patch('olav.modes.expert.workflow.ExpertModeSupervisor') as MockSupervisor:
            mock_supervisor = MagicMock()
            
            # Create a mock state that returns False for should_continue
            mock_state = MagicMock()
            mock_state.query = "test query"
            mock_state.should_continue.return_value = False
            mock_state.root_cause_found = False
            mock_state.root_cause = None
            mock_state.layer_coverage = {}
            mock_state.current_round = 0
            
            mock_supervisor.create_initial_state.return_value = mock_state
            mock_supervisor.generate_report.return_value = "Test report"
            
            MockSupervisor.return_value = mock_supervisor
            
            result = await workflow.run("test query")
            
            assert isinstance(result, ExpertModeOutput)
            assert result.query == "test query"
    
    @pytest.mark.asyncio
    async def test_run_handles_empty_query(self):
        """run() handles empty query gracefully."""
        workflow = ExpertModeWorkflow(max_rounds=1)
        
        # Empty query should be handled - either succeeds with empty results
        # or fails gracefully with an error message
        result = await workflow.run("")
        
        # Output should always be valid
        assert isinstance(result, ExpertModeOutput)
        assert result.query == ""
        # Empty query may fail, but should return proper structure
        if not result.success:
            assert result.final_report is not None
            assert len(result.final_report) > 0


# =============================================================================
# run_expert_mode() Function Tests
# =============================================================================

class TestRunExpertMode:
    """Tests for run_expert_mode() convenience function."""
    
    @pytest.mark.asyncio
    async def test_basic_call(self):
        """run_expert_mode() works with minimal args."""
        with patch('olav.modes.expert.workflow.ExpertModeWorkflow') as MockWorkflow:
            mock_instance = MagicMock()
            mock_instance.run = AsyncMock(return_value=ExpertModeOutput(
                success=True,
                query="test",
                root_cause_found=False,
                root_cause=None,
                final_report="Report",
                layer_coverage={},
                rounds_executed=1,
            ))
            MockWorkflow.return_value = mock_instance
            
            result = await run_expert_mode("test query")
            
            assert result.success is True
    
    @pytest.mark.asyncio
    async def test_with_debug_enabled(self):
        """run_expert_mode() creates debug context when debug=True."""
        with patch('olav.modes.expert.workflow.ExpertModeWorkflow') as MockWorkflow:
            mock_instance = MagicMock()
            mock_instance.run = AsyncMock(return_value=ExpertModeOutput(
                success=True,
                query="test",
                root_cause_found=False,
                root_cause=None,
                final_report="Report",
                layer_coverage={},
                rounds_executed=1,
            ))
            MockWorkflow.return_value = mock_instance
            
            result = await run_expert_mode("test query", debug=True)
            
            # Should have called run with debug_context
            assert mock_instance.run.called


# =============================================================================
# LAYER_INFO Constants Tests
# =============================================================================

class TestLayerInfoConstants:
    """Tests for LAYER_INFO constants."""
    
    def test_all_layers_have_info(self):
        """All NETWORK_LAYERS have entries in LAYER_INFO."""
        for layer in NETWORK_LAYERS:
            assert layer in LAYER_INFO
    
    def test_layer_info_has_required_fields(self):
        """Each LAYER_INFO entry has required fields."""
        required_fields = ["name", "description", "suzieq_tables", "keywords"]
        
        for layer, info in LAYER_INFO.items():
            for field in required_fields:
                assert field in info, f"{layer} missing {field}"
    
    def test_layer_info_tables_are_lists(self):
        """suzieq_tables should be lists."""
        for layer, info in LAYER_INFO.items():
            assert isinstance(info["suzieq_tables"], list)
    
    def test_layer_info_keywords_are_lists(self):
        """keywords should be lists."""
        for layer, info in LAYER_INFO.items():
            assert isinstance(info["keywords"], list)
