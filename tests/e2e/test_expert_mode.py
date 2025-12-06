"""E2E tests for Expert Mode fault diagnosis.

Tests cover:
1. Supervisor state management
2. Layer coverage tracking
3. QuickAnalyzer task execution
4. Full workflow integration
5. Debug context instrumentation
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

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
from olav.modes.shared.debug import DebugContext


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_query() -> str:
    """Sample diagnostic query."""
    return "R1 无法与 R2 建立 BGP 邻居关系"


@pytest.fixture
def sample_devices() -> list[str]:
    """Sample device list."""
    return ["R1", "R2"]


@pytest.fixture
def supervisor() -> ExpertModeSupervisor:
    """Create supervisor instance."""
    return ExpertModeSupervisor(max_rounds=5)


@pytest.fixture
def analyzer() -> QuickAnalyzer:
    """Create quick analyzer instance."""
    return QuickAnalyzer(max_iterations=3)


@pytest.fixture
def workflow() -> ExpertModeWorkflow:
    """Create workflow instance."""
    return ExpertModeWorkflow(max_rounds=3, max_analyzer_iterations=2)


# =============================================================================
# Layer Status Tests
# =============================================================================


class TestLayerStatus:
    """Tests for LayerStatus model."""
    
    def test_initial_state(self):
        """LayerStatus should initialize with defaults."""
        status = LayerStatus(layer="L3")
        
        assert status.layer == "L3"
        assert status.checked is False
        assert status.confidence == 0.0
        assert status.findings == []
        assert status.last_checked is None
    
    def test_update_increases_confidence(self):
        """update() should track max confidence and append findings."""
        status = LayerStatus(layer="L3")
        
        status.update(new_confidence=0.3, new_findings=["Finding 1"])
        assert status.checked is True
        assert status.confidence == 0.3
        assert status.findings == ["Finding 1"]
        assert status.last_checked is not None
        
        # Confidence should take max
        status.update(new_confidence=0.5, new_findings=["Finding 2"])
        assert status.confidence == 0.5
        assert status.findings == ["Finding 1", "Finding 2"]
        
        # Lower confidence should not decrease
        status.update(new_confidence=0.2, new_findings=["Finding 3"])
        assert status.confidence == 0.5
    
    def test_needs_investigation(self):
        """needs_investigation should return True when confidence < 0.5."""
        status = LayerStatus(layer="L3")
        
        assert status.needs_investigation is True
        
        status.update(new_confidence=0.4, new_findings=[])
        assert status.needs_investigation is True
        
        status.update(new_confidence=0.6, new_findings=[])
        assert status.needs_investigation is False


# =============================================================================
# Supervisor State Tests
# =============================================================================


class TestSupervisorState:
    """Tests for SupervisorState model."""
    
    def test_initializes_all_layers(self):
        """State should initialize coverage for all network layers."""
        state = SupervisorState(query="Test query")
        
        assert len(state.layer_coverage) == 4
        for layer in NETWORK_LAYERS:
            assert layer in state.layer_coverage
            assert isinstance(state.layer_coverage[layer], LayerStatus)
    
    def test_get_confidence_gaps(self):
        """get_confidence_gaps() should return layers below threshold."""
        state = SupervisorState(query="Test query")
        
        # Initially all layers have 0 confidence
        gaps = state.get_confidence_gaps()
        assert len(gaps) == 4
        assert all(conf == 0.0 for _, conf in gaps)
        
        # Update some layers
        state.layer_coverage["L1"].update(0.6, [])
        state.layer_coverage["L3"].update(0.3, [])
        
        gaps = state.get_confidence_gaps()
        # L1 is above threshold, L3 is below, L2 and L4 are 0
        layer_names = [layer for layer, _ in gaps]
        assert "L1" not in layer_names
        assert "L3" in layer_names
    
    def test_get_coverage_summary_formatting(self):
        """get_coverage_summary() should return formatted summary."""
        state = SupervisorState(query="Test query")
        state.layer_coverage["L1"].update(0.6, ["Interface up"])
        state.layer_coverage["L3"].update(0.3, ["Route missing"])
        
        summary = state.get_coverage_summary()
        
        assert "Layer Coverage Status" in summary
        assert "L1" in summary
        assert "L3" in summary
        assert "✅" in summary  # L1 above threshold
        assert "⚠️" in summary  # L3 checked but below threshold
        assert "⬜" in summary  # L2, L4 unchecked
    
    def test_should_continue_conditions(self):
        """should_continue() should respect stopping conditions."""
        state = SupervisorState(query="Test query", max_rounds=5)
        
        # Initially should continue (gaps exist)
        assert state.should_continue() is True
        
        # Root cause found -> stop
        state.root_cause_found = True
        assert state.should_continue() is False
        state.root_cause_found = False
        
        # Max rounds reached -> stop
        state.current_round = 5
        assert state.should_continue() is False
        state.current_round = 0
        
        # All layers have sufficient confidence -> stop
        for layer in NETWORK_LAYERS:
            state.layer_coverage[layer].update(0.6, [])
        assert state.should_continue() is False


# =============================================================================
# Supervisor Tests
# =============================================================================


class TestExpertModeSupervisor:
    """Tests for ExpertModeSupervisor."""
    
    def test_create_initial_state(self, supervisor, sample_query, sample_devices):
        """create_initial_state() should initialize properly."""
        state = supervisor.create_initial_state(sample_query, sample_devices)
        
        assert state.query == sample_query
        assert state.path_devices == sample_devices
        assert state.max_rounds == 5
        assert state.current_round == 0
        assert state.root_cause_found is False
    
    @pytest.mark.asyncio
    async def test_round_zero_context_handles_missing_tools(self, supervisor, sample_query):
        """round_zero_context() should handle missing KB/Syslog gracefully."""
        state = supervisor.create_initial_state(sample_query)
        
        # Should not raise even without KB/Syslog tools
        updated_state = await supervisor.round_zero_context(state)
        
        assert isinstance(updated_state.similar_cases, list)
        assert isinstance(updated_state.syslog_events, list)
    
    @pytest.mark.asyncio
    async def test_plan_next_task_returns_lowest_confidence(self, supervisor, sample_query):
        """plan_next_task() should prioritize lowest confidence layer."""
        state = supervisor.create_initial_state(sample_query)
        state.layer_coverage["L1"].update(0.4, [])
        state.layer_coverage["L2"].update(0.1, [])  # Lowest at 0.1
        state.layer_coverage["L3"].update(0.3, [])
        state.layer_coverage["L4"].update(0.2, [])  # Set L4 higher than L2
        
        task = await supervisor.plan_next_task(state)
        
        assert task is not None
        assert task.layer == "L2"  # Lowest confidence first (0.1)
    
    @pytest.mark.asyncio
    async def test_plan_next_task_respects_priority_layer(self, supervisor, sample_query):
        """plan_next_task() should prefer priority_layer from KB."""
        state = supervisor.create_initial_state(sample_query)
        state.priority_layer = "L3"  # KB suggested L3
        
        task = await supervisor.plan_next_task(state)
        
        assert task is not None
        assert task.layer == "L3"  # Priority from KB
    
    @pytest.mark.asyncio
    async def test_plan_next_task_returns_none_when_done(self, supervisor, sample_query):
        """plan_next_task() should return None when investigation complete."""
        state = supervisor.create_initial_state(sample_query)
        state.root_cause_found = True
        
        task = await supervisor.plan_next_task(state)
        
        assert task is None
    
    def test_update_state_tracks_findings(self, supervisor, sample_query):
        """update_state() should update layer coverage."""
        state = supervisor.create_initial_state(sample_query)
        
        result = DiagnosisResult(
            task_id=1,
            layer="L3",
            success=True,
            confidence=0.5,
            findings=["BGP neighbor down", "Route missing"],
        )
        
        updated = supervisor.update_state(state, result)
        
        assert updated.layer_coverage["L3"].confidence == 0.5
        assert len(updated.layer_coverage["L3"].findings) == 2
        assert updated.current_round == 1
    
    def test_update_state_detects_root_cause(self, supervisor, sample_query):
        """update_state() should detect root cause from critical findings."""
        state = supervisor.create_initial_state(sample_query)
        
        result = DiagnosisResult(
            task_id=1,
            layer="L3",
            success=True,
            confidence=0.85,  # High confidence
            findings=["BGP session failed - peer unreachable"],  # Critical keyword
        )
        
        updated = supervisor.update_state(state, result)
        
        assert updated.root_cause_found is True
        assert "failed" in updated.root_cause.lower()
    
    def test_generate_report_format(self, supervisor, sample_query, sample_devices):
        """generate_report() should produce formatted report."""
        state = supervisor.create_initial_state(sample_query, sample_devices)
        state.layer_coverage["L3"].update(0.6, ["BGP neighbor down"])
        state.root_cause_found = True
        state.root_cause = "BGP neighbor down"
        state.current_round = 2
        
        report = supervisor.generate_report(state)
        
        assert "Fault Diagnosis Report" in report
        assert sample_query in report
        assert "Root Cause" in report
        assert "BGP neighbor down" in report
        assert "L3" in report


# =============================================================================
# Quick Analyzer Tests
# =============================================================================


class TestQuickAnalyzer:
    """Tests for QuickAnalyzer."""
    
    def test_initialization(self, analyzer):
        """QuickAnalyzer should initialize with defaults."""
        assert analyzer.max_iterations == 3
        assert analyzer.debug_context is None
        assert analyzer.llm is not None
    
    @pytest.mark.asyncio
    async def test_execute_handles_missing_tools(self, analyzer):
        """execute() should handle missing SuzieQ tools gracefully."""
        task = DiagnosisTask(
            task_id=1,
            layer="L3",
            description="Check BGP state",
            suggested_tables=["bgp", "routes"],
        )
        
        # Mock tools as unavailable
        with patch.object(analyzer, "_get_suzieq_tools", return_value=[]):
            result = await analyzer.execute(task)
        
        assert result.success is False
        assert result.error is not None
        assert "Tools not configured" in result.error
    
    def test_parse_findings_extracts_bullets(self, analyzer):
        """_parse_findings() should extract bullet points."""
        output = """
        Analysis complete:
        - Interface Gi0/0 is down
        - BGP neighbor 10.0.0.1 unreachable
        * Route to 192.168.1.0/24 missing
        
        Additional notes...
        """
        
        findings = analyzer._parse_findings(output)
        
        assert len(findings) == 3
        assert "Interface Gi0/0 is down" in findings
        assert "BGP neighbor 10.0.0.1 unreachable" in findings
    
    def test_parse_findings_captures_error_keywords(self, analyzer):
        """_parse_findings() should capture lines with error keywords."""
        output = """
        The interface check failed with error.
        Normal status here.
        BGP session is down and needs attention.
        """
        
        findings = analyzer._parse_findings(output)
        
        assert any("failed" in f.lower() for f in findings)
        assert any("down" in f.lower() for f in findings)
    
    def test_estimate_confidence_scales_with_findings(self, analyzer):
        """_estimate_confidence() should scale with finding count."""
        # No findings
        assert analyzer._estimate_confidence([]) == 0.0
        
        # Few findings
        conf1 = analyzer._estimate_confidence(["Finding 1"])
        assert 0.0 < conf1 < 0.3
        
        # More findings
        conf2 = analyzer._estimate_confidence(["F1", "F2", "F3", "F4"])
        assert conf2 > conf1
    
    def test_estimate_confidence_boosts_critical_findings(self, analyzer):
        """_estimate_confidence() should boost for critical keywords."""
        normal = analyzer._estimate_confidence(["Normal finding"])
        critical = analyzer._estimate_confidence(["Interface down", "Connection failed"])
        
        assert critical > normal
    
    def test_estimate_confidence_caps_at_suzieq_max(self, analyzer):
        """_estimate_confidence() should cap at SUZIEQ_MAX_CONFIDENCE."""
        from olav.modes.expert.supervisor import SUZIEQ_MAX_CONFIDENCE
        
        many_critical = [
            "Error 1", "Failed 2", "Down 3", "Error 4",
            "Failed 5", "Down 6", "Error 7", "Failed 8",
        ]
        
        conf = analyzer._estimate_confidence(many_critical)
        
        assert conf <= SUZIEQ_MAX_CONFIDENCE


# =============================================================================
# Workflow Tests
# =============================================================================


class TestExpertModeWorkflow:
    """Tests for ExpertModeWorkflow."""
    
    def test_initialization(self, workflow):
        """Workflow should initialize with config."""
        assert workflow.max_rounds == 3
        assert workflow.max_analyzer_iterations == 2
    
    @pytest.mark.asyncio
    async def test_run_returns_expert_mode_output(self, workflow, sample_query):
        """run() should return ExpertModeOutput."""
        with patch.object(
            ExpertModeSupervisor, "round_zero_context", new_callable=AsyncMock
        ) as mock_round_zero:
            # Setup mock
            async def pass_through(state):
                return state
            mock_round_zero.side_effect = pass_through
            
            with patch.object(
                QuickAnalyzer, "execute", new_callable=AsyncMock
            ) as mock_execute:
                # Mock analyzer to return high-confidence result (stops iteration)
                mock_execute.return_value = DiagnosisResult(
                    task_id=1,
                    layer="L1",
                    success=True,
                    confidence=0.9,
                    findings=["Interface check failed - link down"],
                )
                
                result = await workflow.run(sample_query)
        
        assert isinstance(result, ExpertModeOutput)
        assert result.query == sample_query
        assert result.success is True
        assert result.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_run_with_debug_context(self, workflow, sample_query):
        """run() should record debug events when context provided."""
        async with DebugContext(enabled=True) as ctx:
            with patch.object(
                ExpertModeSupervisor, "round_zero_context", new_callable=AsyncMock
            ) as mock_round_zero:
                async def pass_through(state):
                    state.root_cause_found = True  # End early
                    return state
                mock_round_zero.side_effect = pass_through
                
                result = await workflow.run(sample_query, debug_context=ctx)
        
        debug_output = ctx.output
        
        assert debug_output is not None
        assert len(debug_output.graph_states) > 0
        # Should have recorded init and round_zero at minimum
        state_names = [s.node for s in debug_output.graph_states]
        assert any("init" in name for name in state_names)
    
    @pytest.mark.asyncio
    async def test_run_handles_exceptions(self, workflow, sample_query):
        """run() should handle exceptions gracefully."""
        with patch.object(
            ExpertModeSupervisor, "round_zero_context", new_callable=AsyncMock
        ) as mock_round_zero:
            mock_round_zero.side_effect = Exception("Test error")
            
            result = await workflow.run(sample_query)
        
        assert result.success is False
        assert "Test error" in result.final_report
    
    @pytest.mark.asyncio
    async def test_run_respects_max_rounds(self, sample_query):
        """run() should stop after max_rounds."""
        workflow = ExpertModeWorkflow(max_rounds=2)
        
        with patch.object(
            ExpertModeSupervisor, "round_zero_context", new_callable=AsyncMock
        ) as mock_round_zero:
            async def pass_through(state):
                return state
            mock_round_zero.side_effect = pass_through
            
            with patch.object(
                QuickAnalyzer, "execute", new_callable=AsyncMock
            ) as mock_execute:
                # Mock analyzer to return low-confidence (should keep iterating)
                mock_execute.return_value = DiagnosisResult(
                    task_id=1,
                    layer="L1",
                    success=True,
                    confidence=0.2,  # Below threshold
                    findings=["Minor issue"],
                )
                
                result = await workflow.run(sample_query)
        
        assert result.rounds_executed <= 2


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestRunExpertMode:
    """Tests for run_expert_mode() convenience function."""
    
    @pytest.mark.asyncio
    async def test_basic_call(self, sample_query):
        """run_expert_mode() should work with minimal args."""
        with patch.object(
            ExpertModeWorkflow, "run", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = ExpertModeOutput(
                success=True,
                query=sample_query,
                root_cause_found=True,
                root_cause="Test root cause",
                final_report="Test report",
                layer_coverage={},
                rounds_executed=1,
            )
            
            result = await run_expert_mode(sample_query)
        
        assert result.success is True
        mock_run.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_with_debug_enabled(self, sample_query):
        """run_expert_mode() should enable debug context when debug=True."""
        with patch.object(
            ExpertModeWorkflow, "run", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = ExpertModeOutput(
                success=True,
                query=sample_query,
                root_cause_found=False,
                root_cause=None,
                final_report="Test report",
                layer_coverage={},
                rounds_executed=1,
            )
            
            result = await run_expert_mode(sample_query, debug=True)
        
        # Verify debug context was passed
        call_args = mock_run.call_args
        assert call_args[0][1] is None or isinstance(call_args[1].get("debug_context"), DebugContext)


# =============================================================================
# Integration Tests
# =============================================================================


class TestExpertModeIntegration:
    """Integration tests for Expert Mode components."""
    
    @pytest.mark.asyncio
    async def test_full_diagnosis_cycle(self, sample_query, sample_devices):
        """Test complete diagnosis cycle with mocked tools."""
        # Create components
        supervisor = ExpertModeSupervisor(max_rounds=3)
        
        # Initialize state
        state = supervisor.create_initial_state(sample_query, sample_devices)
        assert len(state.layer_coverage) == 4
        
        # Simulate Round 0
        state.priority_layer = "L3"  # KB suggested BGP issue
        
        # Simulate Round 1: Check L3
        task = await supervisor.plan_next_task(state)
        assert task is not None
        assert task.layer == "L3"
        
        result = DiagnosisResult(
            task_id=1,
            layer="L3",
            success=True,
            confidence=0.5,
            findings=["BGP neighbor state: Idle"],
        )
        state = supervisor.update_state(state, result)
        
        assert state.layer_coverage["L3"].confidence == 0.5
        assert state.current_round == 1
        
        # Simulate Round 2: Check remaining layer with lowest confidence
        task = await supervisor.plan_next_task(state)
        assert task is not None
        
        result = DiagnosisResult(
            task_id=2,
            layer=task.layer,
            success=True,
            confidence=0.8,
            findings=["Interface down - BGP peering link failed"],
        )
        state = supervisor.update_state(state, result)
        
        # Root cause should be detected
        assert state.root_cause_found is True
        assert "failed" in state.root_cause.lower()
        
        # Generate report
        report = supervisor.generate_report(state)
        assert "Root Cause" in report
        assert "failed" in report.lower()
    
    def test_layer_info_completeness(self):
        """All NETWORK_LAYERS should have LAYER_INFO entries."""
        for layer in NETWORK_LAYERS:
            assert layer in LAYER_INFO
            info = LAYER_INFO[layer]
            assert "name" in info
            assert "description" in info
            assert "suzieq_tables" in info
            assert "keywords" in info
    
    @pytest.mark.asyncio
    async def test_debug_context_captures_workflow_states(self, sample_query):
        """DebugContext should capture all workflow states."""
        async with DebugContext(enabled=True) as ctx:
            supervisor = ExpertModeSupervisor(max_rounds=2)
            state = supervisor.create_initial_state(sample_query)
            
            # Record manually (simulating workflow)
            ctx.log_graph_state(
                node="expert.init",
                state={"query": sample_query},
            )
            
            ctx.log_graph_state(
                node="expert.round_1",
                state={"layer": "L3", "confidence": 0.5},
            )
        
        output = ctx.output
        
        assert len(output.graph_states) == 2
        assert output.graph_states[0].node == "expert.init"
        assert output.graph_states[1].node == "expert.round_1"


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestExpertModeEdgeCases:
    """Edge case tests for Expert Mode."""
    
    def test_empty_query(self):
        """Supervisor should handle empty query."""
        supervisor = ExpertModeSupervisor()
        state = supervisor.create_initial_state("")
        
        assert state.query == ""
        assert state.should_continue() is True  # Still has confidence gaps
    
    def test_no_devices_specified(self):
        """Workflow should work without specific devices."""
        supervisor = ExpertModeSupervisor()
        state = supervisor.create_initial_state("General network issue")
        
        assert state.path_devices == []
    
    @pytest.mark.asyncio
    async def test_all_layers_checked_stops_iteration(self, sample_query):
        """Workflow should stop when all layers have sufficient confidence."""
        supervisor = ExpertModeSupervisor(max_rounds=10)
        state = supervisor.create_initial_state(sample_query)
        
        # Set all layers to high confidence
        for layer in NETWORK_LAYERS:
            state.layer_coverage[layer].update(0.6, [f"{layer} OK"])
        
        assert state.should_continue() is False
        task = await supervisor.plan_next_task(state)
        assert task is None
    
    def test_diagnosis_result_with_error(self):
        """DiagnosisResult should handle error cases."""
        result = DiagnosisResult(
            task_id=1,
            layer="L3",
            success=False,
            error="Connection timeout",
        )
        
        assert result.success is False
        assert result.error == "Connection timeout"
        assert result.confidence == 0.0
        assert result.findings == []
    
    @pytest.mark.asyncio
    async def test_max_rounds_zero(self, sample_query):
        """Workflow with max_rounds=0 should return immediately."""
        workflow = ExpertModeWorkflow(max_rounds=0)
        
        with patch.object(
            ExpertModeSupervisor, "round_zero_context", new_callable=AsyncMock
        ) as mock_round_zero:
            async def pass_through(state):
                return state
            mock_round_zero.side_effect = pass_through
            
            result = await workflow.run(sample_query)
        
        assert result.rounds_executed == 0
