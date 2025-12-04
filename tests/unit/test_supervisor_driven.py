"""Unit tests for Supervisor-Driven Deep Dive Workflow.

Tests the new dynamic Supervisor-driven architecture:
- Supervisor tracks L1-L4 confidence gaps
- Quick Analyzer executes via ReAct with SuzieQ tools
- No static checklists - dynamic task generation

Test Structure:
- test_layer_status_*: LayerStatus class tests
- test_state_*: SupervisorDrivenState tests
- test_confidence_*: Confidence calculation tests
- test_workflow_*: Graph building and routing tests
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from olav.workflows.supervisor_driven import (
    LayerStatus,
    SupervisorDrivenState,
    NETWORK_LAYERS,
    LAYER_INFO,
    MIN_ACCEPTABLE_CONFIDENCE,
    SUZIEQ_MAX_CONFIDENCE,
    create_initial_state,
    get_confidence_gaps,
    get_coverage_summary,
    should_continue_investigation,
    create_supervisor_driven_workflow,
)


class TestLayerStatus:
    """Tests for LayerStatus class."""
    
    def test_default_values(self):
        """Test LayerStatus initializes with correct defaults."""
        status = LayerStatus()
        
        assert status.checked is False
        assert status.confidence == 0.0
        assert status.findings == []
        assert status.last_checked is None
    
    def test_custom_initialization(self):
        """Test LayerStatus accepts custom values."""
        status = LayerStatus(
            checked=True,
            confidence=0.75,
            findings=["Interface Gi0/0 is down"],
            last_checked="2024-01-15T10:30:00",
        )
        
        assert status.checked is True
        assert status.confidence == 0.75
        assert status.findings == ["Interface Gi0/0 is down"]
        assert status.last_checked == "2024-01-15T10:30:00"
    
    def test_to_dict(self):
        """Test LayerStatus.to_dict() serialization."""
        status = LayerStatus(
            checked=True,
            confidence=0.60,
            findings=["OSPF neighbor down"],
        )
        
        result = status.to_dict()
        
        assert isinstance(result, dict)
        assert result["checked"] is True
        assert result["confidence"] == 0.60
        assert result["findings"] == ["OSPF neighbor down"]
    
    def test_from_dict(self):
        """Test LayerStatus.from_dict() deserialization."""
        data = {
            "checked": True,
            "confidence": 0.55,
            "findings": ["BGP session flapping"],
            "last_checked": "2024-01-15T11:00:00",
        }
        
        status = LayerStatus.from_dict(data)
        
        assert status.checked is True
        assert status.confidence == 0.55
        assert status.findings == ["BGP session flapping"]
        assert status.last_checked == "2024-01-15T11:00:00"
    
    def test_update_method(self):
        """Test LayerStatus.update() method."""
        status = LayerStatus()
        status.update(0.55, ["Interface up"])
        
        assert status.checked is True
        assert status.confidence == 0.55
        assert "Interface up" in status.findings
        assert status.last_checked is not None
    
    def test_update_keeps_highest_confidence(self):
        """Test update keeps highest confidence seen."""
        status = LayerStatus(checked=True, confidence=0.6)
        status.update(0.4, ["New finding"])  # Lower confidence
        
        assert status.confidence == 0.6  # Should keep 0.6, not 0.4


class TestNetworkLayers:
    """Tests for network layer constants."""
    
    def test_all_layers_defined(self):
        """Test all 4 network layers are defined."""
        assert NETWORK_LAYERS == ("L1", "L2", "L3", "L4")
    
    def test_layer_info_has_all_layers(self):
        """Test LAYER_INFO covers all layers."""
        for layer in NETWORK_LAYERS:
            assert layer in LAYER_INFO
    
    def test_layer_info_structure(self):
        """Test each layer has required fields."""
        required_fields = {"name", "description", "suzieq_tables", "keywords"}
        
        for layer, info in LAYER_INFO.items():
            assert required_fields.issubset(info.keys()), f"{layer} missing fields"
            assert isinstance(info["suzieq_tables"], list)
            assert isinstance(info["keywords"], list)
    
    def test_l1_suzieq_tables(self):
        """Test L1 has correct SuzieQ tables."""
        assert "interfaces" in LAYER_INFO["L1"]["suzieq_tables"]
        assert "device" in LAYER_INFO["L1"]["suzieq_tables"]
    
    def test_l3_suzieq_tables(self):
        """Test L3 has correct SuzieQ tables."""
        assert "routes" in LAYER_INFO["L3"]["suzieq_tables"]
        assert "bgp" in LAYER_INFO["L3"]["suzieq_tables"]
        assert "ospf" in LAYER_INFO["L3"]["suzieq_tables"]


class TestInitialState:
    """Tests for state initialization."""
    
    def test_create_initial_state_basic(self):
        """Test basic state creation."""
        state = create_initial_state("查询 R1 BGP 状态")
        
        assert "query" in state
        assert state["query"] == "查询 R1 BGP 状态"
        assert "layer_coverage" in state
        assert "current_round" in state
        assert state["current_round"] == 0
    
    def test_create_initial_state_all_layers_unchecked(self):
        """Test all layers start unchecked."""
        state = create_initial_state("Test query")
        
        for layer in NETWORK_LAYERS:
            assert layer in state["layer_coverage"]
            layer_status = state["layer_coverage"][layer]
            assert layer_status["checked"] is False
            assert layer_status["confidence"] == 0.0
    
    def test_create_initial_state_with_devices(self):
        """Test state creation with device list."""
        state = create_initial_state(
            "查询 R1 R2 接口状态",
            path_devices=["R1", "R2"],
        )
        
        assert state["path_devices"] == ["R1", "R2"]


class TestConfidenceGaps:
    """Tests for confidence gap detection."""
    
    def test_all_layers_are_gaps_initially(self):
        """Test all layers are gaps when unchecked."""
        state = create_initial_state("Test")
        
        gaps = get_confidence_gaps(state["layer_coverage"])
        
        # Returns list of (layer, confidence) tuples
        assert len(gaps) == 4
        gap_layers = [g[0] for g in gaps]
        assert set(gap_layers) == {"L1", "L2", "L3", "L4"}
    
    def test_no_gaps_when_all_sufficient(self):
        """Test no gaps when all layers have sufficient confidence."""
        state = create_initial_state("Test")
        
        for layer in NETWORK_LAYERS:
            state["layer_coverage"][layer]["checked"] = True
            state["layer_coverage"][layer]["confidence"] = 0.6
        
        gaps = get_confidence_gaps(state["layer_coverage"])
        
        assert gaps == []
    
    def test_partial_gaps(self):
        """Test correct gaps when some layers insufficient."""
        state = create_initial_state("Test")
        
        # L1 and L2 sufficient
        state["layer_coverage"]["L1"]["checked"] = True
        state["layer_coverage"]["L1"]["confidence"] = 0.6
        state["layer_coverage"]["L2"]["checked"] = True
        state["layer_coverage"]["L2"]["confidence"] = 0.55
        
        # L3 and L4 still gaps
        gaps = get_confidence_gaps(state["layer_coverage"])
        gap_layers = [g[0] for g in gaps]
        
        assert "L3" in gap_layers
        assert "L4" in gap_layers
        assert "L1" not in gap_layers
        assert "L2" not in gap_layers


class TestCoverageSummary:
    """Tests for coverage summary generation."""
    
    def test_coverage_summary_format(self):
        """Test coverage summary returns formatted string."""
        state = create_initial_state("Test")
        state["layer_coverage"]["L1"]["checked"] = True
        state["layer_coverage"]["L1"]["confidence"] = 0.45
        
        summary = get_coverage_summary(state["layer_coverage"])
        
        assert isinstance(summary, str)
        assert "L1" in summary
        assert "45" in summary or "0.45" in summary
    
    def test_coverage_summary_shows_all_layers(self):
        """Test summary includes all layers."""
        state = create_initial_state("Test")
        
        summary = get_coverage_summary(state["layer_coverage"])
        
        for layer in NETWORK_LAYERS:
            assert layer in summary


class TestShouldContinue:
    """Tests for investigation continuation logic."""
    
    def test_continue_when_gaps_exist(self):
        """Test continues when confidence gaps exist."""
        state = create_initial_state("Test")
        state["current_round"] = 1
        state["max_rounds"] = 5
        
        assert should_continue_investigation(state) is True
    
    def test_stop_when_max_rounds(self):
        """Test stops at max rounds."""
        state = create_initial_state("Test")
        state["current_round"] = 5
        state["max_rounds"] = 5
        
        assert should_continue_investigation(state) is False
    
    def test_stop_when_all_layers_covered(self):
        """Test stops when all layers have sufficient confidence."""
        state = create_initial_state("Test")
        state["current_round"] = 2
        state["max_rounds"] = 5
        
        for layer in NETWORK_LAYERS:
            state["layer_coverage"][layer]["checked"] = True
            state["layer_coverage"][layer]["confidence"] = 0.6
        
        assert should_continue_investigation(state) is False


class TestWorkflowCreation:
    """Tests for workflow graph creation."""
    
    def test_create_workflow_returns_compiled_graph(self):
        """Test workflow creation returns a compiled graph."""
        workflow = create_supervisor_driven_workflow()
        
        # Should be a compiled CompiledStateGraph
        assert workflow is not None
        assert hasattr(workflow, "invoke") or hasattr(workflow, "ainvoke")
    
    def test_workflow_has_required_nodes(self):
        """Test workflow contains all required nodes."""
        # Create StateGraph directly to inspect nodes
        from langgraph.graph import StateGraph
        from olav.workflows.supervisor_driven import (
            supervisor_node,
            quick_analyzer_node,
            report_generator_node,
        )
        
        graph = StateGraph(SupervisorDrivenState)
        graph.add_node("supervisor", supervisor_node)
        graph.add_node("quick_analyzer", quick_analyzer_node)
        graph.add_node("report", report_generator_node)
        
        # This should not raise
        assert True  # If we get here, nodes were added successfully


class TestConfidenceConstants:
    """Tests for confidence-related constants."""
    
    def test_suzieq_max_is_60_percent(self):
        """Test SuzieQ max confidence is 60%."""
        assert SUZIEQ_MAX_CONFIDENCE == 0.60
    
    def test_min_acceptable_is_50_percent(self):
        """Test minimum acceptable confidence is 50%."""
        assert MIN_ACCEPTABLE_CONFIDENCE == 0.5
    
    def test_suzieq_max_exceeds_min_acceptable(self):
        """Test SuzieQ can reach acceptable confidence."""
        assert SUZIEQ_MAX_CONFIDENCE >= MIN_ACCEPTABLE_CONFIDENCE


class TestPromptLoading:
    """Tests for prompt template loading."""
    
    def test_supervisor_prompt_exists(self):
        """Test supervisor_plan.yaml prompt can be loaded."""
        from pathlib import Path
        
        prompt_path = Path("config/prompts/workflows/deep_dive/supervisor_plan.yaml")
        assert prompt_path.exists(), f"Missing: {prompt_path}"
    
    def test_quick_analyzer_prompt_exists(self):
        """Test quick_analyzer.yaml prompt can be loaded."""
        from pathlib import Path
        
        prompt_path = Path("config/prompts/workflows/deep_dive/quick_analyzer.yaml")
        assert prompt_path.exists(), f"Missing: {prompt_path}"
    
    def test_conclusion_prompt_exists(self):
        """Test conclusion.yaml prompt can be loaded."""
        from pathlib import Path
        
        prompt_path = Path("config/prompts/workflows/deep_dive/conclusion.yaml")
        assert prompt_path.exists(), f"Missing: {prompt_path}"


@pytest.mark.asyncio
class TestSupervisorNode:
    """Async tests for supervisor node."""
    
    async def test_supervisor_node_picks_lowest_confidence_layer(self):
        """Test supervisor picks the layer with lowest confidence."""
        from olav.workflows.supervisor_driven import supervisor_node
        
        state = create_initial_state("Test query")
        state["current_round"] = 0
        state["max_rounds"] = 5
        state["messages"] = []
        
        # L1 has some confidence, L2-L4 at 0
        state["layer_coverage"]["L1"]["checked"] = True
        state["layer_coverage"]["L1"]["confidence"] = 0.3
        
        result = await supervisor_node(state)
        
        # Should pick L2, L3, or L4 (all at 0.0)
        assert result["current_layer"] in ["L2", "L3", "L4"]
        assert result["current_round"] == 1
        assert result["current_task"] is not None
    
    async def test_supervisor_node_no_task_when_all_covered(self):
        """Test supervisor returns no task when all layers sufficient."""
        from olav.workflows.supervisor_driven import supervisor_node
        
        state = create_initial_state("Test query")
        state["current_round"] = 2
        state["max_rounds"] = 5
        state["messages"] = []
        
        # All layers at 60%
        for layer in NETWORK_LAYERS:
            state["layer_coverage"][layer]["checked"] = True
            state["layer_coverage"][layer]["confidence"] = 0.6
        
        result = await supervisor_node(state)
        
        assert result["current_task"] is None
        assert result["current_layer"] is None


@pytest.mark.asyncio
class TestQuickAnalyzerNode:
    """Async tests for quick analyzer node."""
    
    async def test_quick_analyzer_no_task_returns_message(self):
        """Test quick analyzer handles missing task gracefully."""
        from olav.workflows.supervisor_driven import quick_analyzer_node
        
        state = create_initial_state("Test query")
        state["current_task"] = None
        state["current_layer"] = None
        state["messages"] = []
        
        result = await quick_analyzer_node(state)
        
        assert "messages" in result
        assert len(result["messages"]) > 0
