"""Unit tests for Standard Mode components.

Tests:
- StandardModeClassifier: LLM-based classification with fallback
- StandardModeExecutor: Tool execution with HITL detection
- StandardModeWorkflow: End-to-end orchestration
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from olav.modes.standard import (
    StandardModeClassifier,
    StandardModeExecutor,
    StandardModeResult,
    ExecutionResult,
    HITLRequired,
)
from olav.core.unified_classifier import UnifiedClassificationResult
from olav.tools.base import ToolOutput, ToolRegistry


# ============================================
# Fixtures
# ============================================

@pytest.fixture
def mock_classification_result():
    """Create a mock classification result."""
    return UnifiedClassificationResult(
        intent_category="suzieq",
        tool="suzieq_query",
        parameters={"table": "bgp", "hostname": "R1"},
        confidence=0.95,
        reasoning=None,
    )


@pytest.fixture
def mock_tool_registry():
    """Create mock tool registry with fake tools."""
    registry = MagicMock(spec=ToolRegistry)
    
    # Mock tool that returns successful output
    mock_tool = MagicMock()
    mock_tool.execute = AsyncMock(return_value=ToolOutput(
        success=True,
        data=[{"state": "Established", "peerHostname": "R2"}],
        error=None,
        source="suzieq",
        device="R1",
    ))
    
    registry.get_tool.return_value = mock_tool
    return registry


@pytest.fixture
def executor(mock_tool_registry):
    """Create StandardModeExecutor with mock registry."""
    return StandardModeExecutor(
        tool_registry=mock_tool_registry,
        yolo_mode=True,  # Skip HITL for most tests
    )


# ============================================
# StandardModeClassifier Tests
# ============================================

class TestStandardModeClassifier:
    """Test StandardModeClassifier functionality."""
    
    @pytest.mark.asyncio
    async def test_classify_returns_result(self):
        """Test classifier returns UnifiedClassificationResult."""
        with patch('olav.modes.standard.classifier.UnifiedClassifier') as MockClassifier:
            mock_instance = MockClassifier.return_value
            mock_instance.classify = AsyncMock(return_value=UnifiedClassificationResult(
                intent_category="suzieq",
                tool="suzieq_query",
                parameters={"table": "bgp"},
                confidence=0.9,
                reasoning=None,
            ))
            
            classifier = StandardModeClassifier()
            result = await classifier.classify("查询 R1 BGP 状态")
            
            assert result.intent_category == "suzieq"
            assert result.tool == "suzieq_query"
            assert result.confidence >= 0.0
    
    def test_should_escalate_low_confidence(self):
        """Test escalation when confidence is below threshold."""
        classifier = StandardModeClassifier(confidence_threshold=0.7)
        
        result = UnifiedClassificationResult(
            intent_category="suzieq",
            tool="suzieq_query",
            parameters={},
            confidence=0.5,  # Below threshold
            reasoning=None,
        )
        
        assert classifier.should_escalate_to_expert(result) is True
    
    def test_should_not_escalate_high_confidence(self):
        """Test no escalation when confidence is above threshold."""
        classifier = StandardModeClassifier(confidence_threshold=0.7)
        
        result = UnifiedClassificationResult(
            intent_category="suzieq",
            tool="suzieq_query",
            parameters={},
            confidence=0.9,  # Above threshold
            reasoning=None,
        )
        
        assert classifier.should_escalate_to_expert(result) is False


# ============================================
# StandardModeExecutor Tests
# ============================================

class TestStandardModeExecutor:
    """Test StandardModeExecutor functionality."""
    
    @pytest.mark.asyncio
    async def test_execute_success(self, executor, mock_classification_result):
        """Test successful tool execution."""
        result = await executor.execute(
            classification=mock_classification_result,
            user_query="查询 R1 BGP 状态",
        )
        
        assert result.success is True
        assert result.tool_name == "suzieq_query"
        assert result.execution_time_ms > 0
    
    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self, mock_tool_registry, mock_classification_result):
        """Test execution when tool is not found."""
        mock_tool_registry.get_tool.return_value = None
        executor = StandardModeExecutor(
            tool_registry=mock_tool_registry,
            yolo_mode=True,
        )
        
        result = await executor.execute(
            classification=mock_classification_result,
            user_query="查询 R1 BGP 状态",
        )
        
        assert result.success is False
        assert "not found" in result.error.lower()
    
    def test_requires_hitl_netbox_post(self, executor):
        """Test HITL detection for NetBox POST."""
        requires, reason = executor._requires_hitl(
            tool_name="netbox_api_call",
            parameters={"method": "POST", "path": "/dcim/devices/"},
        )
        
        # yolo_mode=True skips HITL
        assert requires is False
    
    def test_requires_hitl_netbox_post_strict(self, mock_tool_registry):
        """Test HITL detection for NetBox POST in strict mode."""
        executor = StandardModeExecutor(
            tool_registry=mock_tool_registry,
            yolo_mode=False,  # Strict mode
        )
        
        requires, reason = executor._requires_hitl(
            tool_name="netbox_api_call",
            parameters={"method": "POST", "path": "/dcim/devices/"},
        )
        
        assert requires is True
        assert "POST" in reason
    
    def test_requires_hitl_netconf_edit(self, mock_tool_registry):
        """Test HITL detection for NETCONF edit-config."""
        executor = StandardModeExecutor(
            tool_registry=mock_tool_registry,
            yolo_mode=False,
        )
        
        requires, reason = executor._requires_hitl(
            tool_name="netconf_tool",
            parameters={"operation": "edit-config"},
        )
        
        assert requires is True
    
    def test_requires_hitl_netconf_get(self, mock_tool_registry):
        """Test no HITL for NETCONF get (read-only)."""
        executor = StandardModeExecutor(
            tool_registry=mock_tool_registry,
            yolo_mode=False,
        )
        
        requires, reason = executor._requires_hitl(
            tool_name="netconf_tool",
            parameters={"operation": "get"},
        )
        
        assert requires is False
    
    def test_parameter_mapping(self, executor):
        """Test parameter name mapping for LLM compatibility."""
        params = {"endpoint": "/dcim/devices/", "filters": {"name": "R1"}}
        mapped = executor._map_parameters("netbox_api_call", params)
        
        assert "path" in mapped
        assert "params" in mapped
        assert mapped["path"] == "/dcim/devices/"


# ============================================
# Integration Tests (with mocks)
# ============================================

class TestStandardModeIntegration:
    """Integration tests for Standard Mode workflow."""
    
    @pytest.mark.asyncio
    async def test_run_standard_mode_success(self, mock_tool_registry):
        """Test complete standard mode execution."""
        with patch('olav.modes.standard.workflow.StandardModeClassifier') as MockClassifier:
            mock_classifier = MockClassifier.return_value
            mock_classifier.classify = AsyncMock(return_value=UnifiedClassificationResult(
                intent_category="suzieq",
                tool="suzieq_query",
                parameters={"table": "bgp", "hostname": "R1"},
                confidence=0.9,
                reasoning=None,
            ))
            mock_classifier.should_escalate_to_expert.return_value = False
            
            from olav.modes.standard import run_standard_mode
            
            result = await run_standard_mode(
                query="查询 R1 BGP 状态",
                tool_registry=mock_tool_registry,
                yolo_mode=True,
            )
            
            assert isinstance(result, StandardModeResult)
            assert result.escalated_to_expert is False
    
    @pytest.mark.asyncio
    async def test_run_standard_mode_escalates(self, mock_tool_registry):
        """Test standard mode escalation to expert."""
        with patch('olav.modes.standard.workflow.StandardModeClassifier') as MockClassifier:
            mock_classifier = MockClassifier.return_value
            mock_classifier.classify = AsyncMock(return_value=UnifiedClassificationResult(
                intent_category="suzieq",
                tool="suzieq_query",
                parameters={},
                confidence=0.4,  # Low confidence
                reasoning=None,
            ))
            mock_classifier.should_escalate_to_expert.return_value = True
            
            from olav.modes.standard import run_standard_mode
            
            result = await run_standard_mode(
                query="为什么 BGP 邻居建不起来?",
                tool_registry=mock_tool_registry,
                yolo_mode=True,
            )
            
            assert result.escalated_to_expert is True
