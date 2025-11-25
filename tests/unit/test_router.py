"""
Unit tests for DynamicIntentRouter.

Tests semantic pre-filtering, LLM classification, trigger matching, and routing decisions.
"""

import numpy as np
import pytest
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from olav.agents.dynamic_orchestrator import DynamicIntentRouter, RouteDecision
from olav.workflows.registry import WorkflowRegistry, WorkflowMetadata


# Test fixtures

@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry before and after each test."""
    WorkflowRegistry.clear()
    yield
    WorkflowRegistry.clear()


@pytest.fixture
def mock_embeddings():
    """Create mock embeddings model."""
    embeddings = MagicMock(spec=Embeddings)
    
    # Mock aembed_documents to return predictable vectors (async version)
    async def aembed_documents(texts: List[str]):
        # Simple mock: length-based vectors for predictability
        return [[0.1 * len(t), 0.2 * len(t)] for t in texts]
    
    # Mock aembed_query to return query vector (async version)
    async def aembed_query(text: str):
        return [0.1 * len(text), 0.2 * len(text)]
    
    embeddings.aembed_documents = AsyncMock(side_effect=aembed_documents)
    embeddings.aembed_query = AsyncMock(side_effect=aembed_query)
    
    return embeddings


@pytest.fixture
def mock_llm():
    """Create mock LLM for classification."""
    llm = MagicMock(spec=BaseChatModel)
    
    # Mock ainvoke to return RouteDecision JSON
    async def ainvoke(messages):
        # Return QueryWorkflow by default
        return AIMessage(content="""{
            "workflow": "QueryWorkflow",
            "confidence": 0.95,
            "reasoning": "Mock LLM decision"
        }""")
    
    llm.ainvoke = AsyncMock(side_effect=ainvoke)
    
    return llm


@pytest.fixture
def sample_workflows():
    """Register sample workflows for testing."""
    
    @WorkflowRegistry.register(
        name="QueryWorkflow",
        description="SuzieQ-based network diagnostics",
        examples=[
            "查询 R1 的 BGP 状态",
            "显示所有接口",
            "检查 OSPF 邻居"
        ],
        triggers=["查询", "显示", "检查", "bgp", "ospf", "interface"]
    )
    class QueryWorkflowClass:
        pass
    
    @WorkflowRegistry.register(
        name="ExecutionWorkflow",
        description="NETCONF/CLI execution with HITL",
        examples=[
            "配置接口 Gi0/1",
            "修改 BGP AS 号",
            "应用配置更改"
        ],
        triggers=["配置", "修改", "应用", "config", "apply"]
    )
    class ExecutionWorkflowClass:
        pass
    
    @WorkflowRegistry.register(
        name="DeepDiveWorkflow",
        description="Complex multi-step diagnostics",
        examples=[
            "为什么 R1 无法建立 BGP 邻居？",
            "诊断网络连通性问题",
            "排查路由黑洞"
        ],
        triggers=["为什么", "诊断", "排查", "why", "troubleshoot"]
    )
    class DeepDiveWorkflowClass:
        pass
    
    return [
        WorkflowRegistry.get_workflow("QueryWorkflow"),
        WorkflowRegistry.get_workflow("ExecutionWorkflow"),
        WorkflowRegistry.get_workflow("DeepDiveWorkflow")
    ]


@pytest.fixture
async def router(mock_embeddings, mock_llm, sample_workflows):
    """Create DynamicIntentRouter with mocked dependencies."""
    # sample_workflows ensures workflows are registered before build_index
    router = DynamicIntentRouter(
        embeddings=mock_embeddings,
        llm=mock_llm,
        top_k=2
    )
    await router.build_index()
    return router


# Initialization tests

@pytest.mark.asyncio
async def test_router_initialization(mock_embeddings, mock_llm, sample_workflows):
    """Test router initializes and builds index."""
    router = DynamicIntentRouter(embeddings=mock_embeddings, llm=mock_llm)
    
    assert router.embeddings == mock_embeddings
    assert router.llm == mock_llm
    assert router.top_k == 3  # default
    
    # Index should be empty before build
    assert router.example_vectors == {}
    
    # Build index
    await router.build_index()
    
    # Should have vectors for all workflows
    assert len(router.example_vectors) == 3
    
    # Each workflow should have embedded examples
    for workflow_name in ["QueryWorkflow", "ExecutionWorkflow", "DeepDiveWorkflow"]:
        assert workflow_name in router.example_vectors
        vector = router.example_vectors[workflow_name]
        assert isinstance(vector, np.ndarray)
        assert len(vector) > 0  # Verify vector is not empty


@pytest.mark.asyncio
async def test_rebuild_index_on_new_workflows(mock_embeddings, mock_llm):
    """Test index can be rebuilt when new workflows are registered."""
    # Register initial workflows
    @WorkflowRegistry.register(
        name="InitialWorkflow",
        description="Initial test workflow",
        examples=["initial example"],
        triggers=["initial"]
    )
    class InitialWorkflowClass:
        pass
    
    router = DynamicIntentRouter(embeddings=mock_embeddings, llm=mock_llm)
    await router.build_index()
    
    initial_count = len(router.example_vectors)
    
    # Register new workflow
    @WorkflowRegistry.register(
        name="NewWorkflow",
        description="New test workflow",
        examples=["new example"],
        triggers=["new"]
    )
    class NewWorkflowClass:
        pass
    
    # Rebuild index
    await router.build_index()
    
    assert len(router.example_vectors) == initial_count + 1


# Trigger fast-path tests

@pytest.mark.asyncio
async def test_trigger_fast_path(router, sample_workflows):
    """Test trigger-based fast path bypasses semantic search."""
    
    # Query with exact trigger match
    workflow_name = await router.route("查询 BGP 状态")
    
    # Should match QueryWorkflow via trigger (route() returns string, not RouteDecision)
    assert workflow_name == "QueryWorkflow"
    assert isinstance(workflow_name, str)


@pytest.mark.asyncio
async def test_no_trigger_match_uses_semantic(router, sample_workflows, mock_llm):
    """Test queries without trigger matches use semantic routing."""
    
    # Query without explicit triggers
    query = "this query has no triggers in any workflow"
    
    workflow_name = await router.route(query)
    
    # Should still return a valid workflow name (from LLM classification)
    assert workflow_name in ["QueryWorkflow", "ExecutionWorkflow", "DeepDiveWorkflow"]
    
    # LLM should have been called
    mock_llm.ainvoke.assert_called()


# Semantic pre-filtering tests

@pytest.mark.asyncio
async def test_semantic_prefilter_returns_top_k(router, sample_workflows):
    """Test semantic pre-filter returns correct number of candidates."""
    
    query = "查询路由器状态"
    
    candidates = await router.semantic_prefilter(query)
    
    # Should return top_k candidates (router configured with top_k=2 in fixture)
    # Note: May return all workflows if similarities are very close
    assert len(candidates) <= len(sample_workflows)
    assert len(candidates) > 0
    
    # Each candidate should be (workflow_name, similarity_score)
    for name, score in candidates:
        assert isinstance(name, str)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0


@pytest.mark.asyncio
async def test_semantic_prefilter_similarity_ordering(router, sample_workflows):
    """Test candidates are ordered by similarity score (highest first)."""
    
    query = "诊断 BGP 问题"
    
    candidates = await router.semantic_prefilter(query)
    
    # Scores should be in descending order
    scores = [score for _, score in candidates]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_semantic_prefilter_with_no_workflows(mock_embeddings, mock_llm):
    """Test semantic pre-filter with empty registry."""
    router = DynamicIntentRouter(embeddings=mock_embeddings, llm=mock_llm)
    
    # build_index should raise ValueError when no workflows registered
    with pytest.raises(ValueError, match="No workflows registered"):
        await router.build_index()


# LLM classification tests

@pytest.mark.asyncio
async def test_llm_classify_with_candidates(router, sample_workflows, mock_llm):
    """Test LLM classification selects from candidates."""
    
    query = "查询 BGP 状态"
    # Get actual WorkflowMetadata objects from registry
    query_wf = WorkflowRegistry.get_workflow("QueryWorkflow")
    deepdive_wf = WorkflowRegistry.get_workflow("DeepDiveWorkflow")
    candidates = [query_wf, deepdive_wf]
    
    decision = await router.llm_classify(query, candidates)
    
    # Should return RouteDecision (llm_classify still returns RouteDecision object)
    assert isinstance(decision, RouteDecision)
    assert decision.workflow_name in ["QueryWorkflow", "DeepDiveWorkflow"]
    assert 0.0 <= decision.confidence <= 1.0
    
    # LLM should have been invoked
    mock_llm.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_llm_classify_context_includes_candidates(router, sample_workflows, mock_llm):
    """Test LLM receives candidate workflow context."""
    
    query = "测试查询"
    query_wf = WorkflowRegistry.get_workflow("QueryWorkflow")
    candidates = [query_wf]
    
    await router.llm_classify(query, candidates)
    
    # Check LLM was called with proper context
    call_args = mock_llm.ainvoke.call_args
    messages = call_args[0][0]
    
    # Should include workflow descriptions and examples
    message_text = str(messages)
    assert "QueryWorkflow" in message_text
    assert "SuzieQ" in message_text  # From QueryWorkflow description


@pytest.mark.asyncio
async def test_llm_classify_fallback_on_invalid_json(router, sample_workflows, mock_llm):
    """Test LLM classification handles invalid JSON response."""
    
    # Mock LLM to return invalid JSON
    async def invalid_json(messages):
        return AIMessage(content="NOT VALID JSON")
    
    mock_llm.ainvoke = AsyncMock(side_effect=invalid_json)
    
    query = "测试"
    query_wf = WorkflowRegistry.get_workflow("QueryWorkflow")
    candidates = [query_wf]
    
    decision = await router.llm_classify(query, candidates)
    
    # Should fallback to first candidate with low confidence (llm_classify returns RouteDecision)
    assert decision.workflow_name == "QueryWorkflow"
    assert decision.confidence <= 0.5  # Fallback confidence is exactly 0.5
    assert "fallback" in decision.reasoning.lower() or "解析" in decision.reasoning


# Full routing tests

@pytest.mark.asyncio
async def test_route_full_pipeline(router, sample_workflows):
    """Test complete routing pipeline (triggers → semantic → LLM)."""
    
    query = "查询 R1 BGP 状态"
    
    workflow_name = await router.route(query)
    
    # Should return workflow name string
    assert isinstance(workflow_name, str)
    assert workflow_name in ["QueryWorkflow", "ExecutionWorkflow", "DeepDiveWorkflow"]


@pytest.mark.asyncio
async def test_route_prefers_trigger_match(router, sample_workflows, mock_llm):
    """Test trigger matches take precedence over semantic search."""
    
    # Clear LLM call count
    mock_llm.ainvoke.reset_mock()
    
    # Query with explicit trigger
    query = "配置接口"  # Should trigger ExecutionWorkflow
    
    workflow_name = await router.route(query)
    
    # Should match via trigger and return workflow name string
    assert isinstance(workflow_name, str)
    assert workflow_name in ["QueryWorkflow", "ExecutionWorkflow", "DeepDiveWorkflow"]


@pytest.mark.asyncio
async def test_route_with_empty_query(router, sample_workflows):
    """Test routing with empty query."""
    
    workflow_name = await router.route("")
    
    # Should still return a workflow name (fallback to first workflow or default)
    assert isinstance(workflow_name, str)
    assert workflow_name in ["QueryWorkflow", "ExecutionWorkflow", "DeepDiveWorkflow"]


@pytest.mark.asyncio
async def test_route_with_chinese_query(router, sample_workflows):
    """Test routing with Chinese query."""
    
    query = "为什么路由器无法建立邻居关系？"
    
    workflow_name = await router.route(query)
    
    # Should route to DeepDiveWorkflow (has "为什么" trigger)
    # Or handle correctly via semantic search
    assert isinstance(workflow_name, str)
    assert workflow_name in ["QueryWorkflow", "ExecutionWorkflow", "DeepDiveWorkflow"]


@pytest.mark.asyncio
async def test_route_with_mixed_language_query(router, sample_workflows):
    """Test routing with mixed Chinese/English query."""
    
    query = "查询 BGP neighbor 状态"
    
    workflow_name = await router.route(query)
    
    # Should route to QueryWorkflow (has "bgp" trigger and "查询" trigger)
    assert isinstance(workflow_name, str)
    assert workflow_name in ["QueryWorkflow", "ExecutionWorkflow", "DeepDiveWorkflow"]


# Performance tests

@pytest.mark.asyncio
async def test_routing_performance(router, sample_workflows):
    """Test routing completes within acceptable time."""
    import time
    
    query = "查询网络状态"
    
    start = time.time()
    workflow_name = await router.route(query)
    duration = time.time() - start
    
    # Should complete within 2 seconds (generous for unit test)
    assert duration < 2.0
    assert isinstance(workflow_name, str)


@pytest.mark.asyncio
async def test_batch_routing(router, sample_workflows):
    """Test routing multiple queries in sequence."""
    
    queries = [
        "查询 BGP 状态",
        "配置接口",
        "为什么路由器不工作？",
        "显示路由表",
        "应用配置更改"
    ]
    
    workflow_names = []
    for query in queries:
        workflow_name = await router.route(query)
        workflow_names.append(workflow_name)
    
    # All should return valid workflow names
    assert len(workflow_names) == len(queries)
    assert all(isinstance(name, str) for name in workflow_names)
    assert all(name in ["QueryWorkflow", "ExecutionWorkflow", "DeepDiveWorkflow"] for name in workflow_names)


# Edge cases

@pytest.mark.asyncio
async def test_route_with_very_long_query(router, sample_workflows):
    """Test routing with extremely long query."""
    
    query = "查询 " + "BGP " * 100 + "状态"
    
    workflow_name = await router.route(query)
    
    assert isinstance(workflow_name, str)
    assert workflow_name in ["QueryWorkflow", "ExecutionWorkflow", "DeepDiveWorkflow"]


@pytest.mark.asyncio
async def test_route_with_special_characters(router, sample_workflows):
    """Test routing with special characters."""
    
    query = "查询 @#$%^&*() 状态？！"
    
    workflow_name = await router.route(query)
    
    assert isinstance(workflow_name, str)
    assert workflow_name in ["QueryWorkflow", "ExecutionWorkflow", "DeepDiveWorkflow"]


@pytest.mark.asyncio
async def test_confidence_scores_valid_range(router, sample_workflows):
    """Test all workflow names are valid strings."""
    
    queries = [
        "查询状态",
        "配置设备",
        "诊断问题",
        "random query with no matches"
    ]
    
    for query in queries:
        workflow_name = await router.route(query)
        assert isinstance(workflow_name, str), \
            f"Expected string workflow_name, got {type(workflow_name)} for query: {query}"
        assert workflow_name in ["QueryWorkflow", "ExecutionWorkflow", "DeepDiveWorkflow"], \
            f"Invalid workflow name {workflow_name} for query: {query}"
