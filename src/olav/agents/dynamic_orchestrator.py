"""
Dynamic Intent Router - Two-Phase Workflow Selection.

This module implements intelligent workflow routing using a two-phase approach:
1. Semantic Pre-filtering: Vector similarity on workflow examples (fast)
2. LLM Classification: Precise routing on Top-3 candidates (accurate)

Advantages over hardcoded routing:
- Zero-invasive extensibility: New workflows auto-register via decorator
- High accuracy: Combines semantic understanding with LLM reasoning
- Low latency: Pre-filtering reduces LLM context length
- Maintainability: Intent examples live with workflow definitions

Usage:
    router = DynamicIntentRouter(llm_factory, embeddings_factory)
    await router.build_index()  # One-time at startup
    workflow_name = await router.route("查询 R1 的 BGP 状态")
"""

import logging

import numpy as np
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field
from sklearn.metrics.pairwise import cosine_similarity

from olav.workflows.registry import WorkflowMetadata, WorkflowRegistry

logger = logging.getLogger(__name__)


class RouteDecision(BaseModel):
    """LLM routing decision output."""

    workflow_name: str = Field(description="Selected workflow identifier")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0", ge=0.0, le=1.0)
    reasoning: str = Field(description="Brief explanation for the selection")


class DynamicIntentRouter:
    """
    Two-phase workflow router combining semantic search and LLM classification.

    Phase 1: Semantic Pre-filtering
        - Compute query embedding
        - Compare with pre-computed workflow example vectors
        - Return Top-K most similar workflows (default K=3)

    Phase 2: LLM Classification
        - Construct classification prompt with Top-K candidates only
        - LLM makes final decision based on descriptions and query
        - Returns workflow name with confidence score

    Attributes:
        llm: Language model for final classification
        embeddings: Embedding model for semantic similarity
        example_vectors: Pre-computed average vectors for workflow examples
        trigger_cache: Compiled regex patterns for keyword matching
    """

    def __init__(self, llm: BaseChatModel, embeddings: Embeddings, top_k: int = 3) -> None:
        """
        Initialize router with models and configuration.

        Args:
            llm: Language model for classification (should support JSON mode)
            embeddings: Embedding model for semantic similarity
            top_k: Number of candidates for LLM classification
        """
        self.llm = llm
        self.embeddings = embeddings
        self.top_k = top_k
        self.example_vectors: dict[str, np.ndarray] = {}
        self.registry = WorkflowRegistry

        logger.info(
            f"Initialized DynamicIntentRouter with {top_k} candidates, "
            f"LLM: {type(llm).__name__}, Embeddings: {type(embeddings).__name__}"
        )

    async def build_index(self) -> None:
        """
        Build semantic index for all registered workflows.

        This should be called once at startup. Computes average embedding
        vector for each workflow's example queries.

        Raises:
            ValueError: If no workflows are registered
        """
        workflows = self.registry.list_workflows()

        if not workflows:
            msg = (
                "No workflows registered. Ensure workflows are decorated "
                "with @WorkflowRegistry.register before router initialization."
            )
            raise ValueError(msg)

        logger.info(f"Building semantic index for {len(workflows)} workflows...")

        for metadata in workflows:
            if not metadata.examples:
                logger.warning(
                    f"Workflow '{metadata.name}' has no examples, using description for embedding"
                )
                texts = [metadata.description]
            else:
                texts = metadata.examples

            # Compute embeddings for all examples
            vectors = await self.embeddings.aembed_documents(texts)

            # Average pooling: mean of all example vectors
            avg_vector = np.mean(vectors, axis=0)
            self.example_vectors[metadata.name] = avg_vector

            logger.debug(
                f"Indexed workflow '{metadata.name}' with "
                f"{len(texts)} examples, vector dim: {len(avg_vector)}"
            )

        logger.info(
            f"Semantic index built successfully. "
            f"Vector dimension: {len(next(iter(self.example_vectors.values())))}"
        )

    async def semantic_prefilter(self, query: str) -> list[tuple[str, float]]:
        """
        Phase 1: Semantic pre-filtering using cosine similarity.

        Args:
            query: User query string

        Returns:
            List of (workflow_name, similarity_score) tuples, sorted by score

        Raises:
            RuntimeError: If semantic index not built (call build_index first)
        """
        if not self.example_vectors:
            msg = "Semantic index not built. Call build_index() first."
            raise RuntimeError(msg)

        # Compute query embedding
        query_vector = await self.embeddings.aembed_query(query)
        query_array = np.array([query_vector])

        # Compute cosine similarity with all workflow vectors
        similarities: list[tuple[str, float]] = []

        for name, workflow_vector in self.example_vectors.items():
            vector_array = np.array([workflow_vector])
            similarity = cosine_similarity(query_array, vector_array)[0][0]
            similarities.append((name, float(similarity)))

        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)

        logger.debug(
            f"Semantic pre-filtering results: "
            f"{[(name, f'{score:.3f}') for name, score in similarities[: self.top_k]]}"
        )

        return similarities

    async def llm_classify(self, query: str, candidates: list[WorkflowMetadata]) -> RouteDecision:
        """
        Phase 2: LLM-based classification on Top-K candidates.

        Args:
            query: User query string
            candidates: List of candidate workflow metadata (Top-K from phase 1)

        Returns:
            Routing decision with workflow name, confidence, and reasoning
        """
        # Build classification prompt
        candidates_desc = "\n".join(
            [f"{i + 1}. **{c.name}**: {c.description}" for i, c in enumerate(candidates)]
        )

        prompt = f"""你是 OLAV 网络运维平台的意图路由器。根据用户查询，从候选工作流中选择最合适的一个。

用户查询: {query}

候选工作流:
{candidates_desc}

请分析查询意图，选择最匹配的工作流。如果查询意图不明确或不属于任何候选工作流，选择置信度最高的候选。

返回 JSON 格式:
{{
    "workflow_name": "选中的工作流名称（必须是候选之一）",
    "confidence": 0.95,
    "reasoning": "简短说明选择原因"
}}
"""

        # Invoke LLM with JSON mode
        response = await self.llm.ainvoke(prompt)

        # Parse response (assuming LLM returns JSON)
        try:
            decision = RouteDecision.model_validate_json(response.content)
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {response.content}")
            # Fallback: select first candidate
            decision = RouteDecision(
                workflow_name=candidates[0].name,
                confidence=0.5,
                reasoning=f"Fallback selection due to parse error: {e}",
            )

        logger.info(
            f"LLM classification: {decision.workflow_name} "
            f"(confidence: {decision.confidence:.2f}) - {decision.reasoning}"
        )

        return decision

    async def route(self, user_query: str, fallback: str | None = None) -> str:
        """
        Main routing method combining both phases.

        Args:
            user_query: User's natural language query
            fallback: Workflow name to use if routing fails (default: first registered)

        Returns:
            Selected workflow name

        Raises:
            ValueError: If no workflows are registered
        """
        # Check for keyword triggers first (fast path)
        trigger_matches = self.registry.match_triggers(user_query)
        if trigger_matches:
            logger.info(
                f"Trigger match found for query: {trigger_matches[0]} (skipping semantic routing)"
            )
            return trigger_matches[0]

        # Phase 1: Semantic pre-filtering
        similarities = await self.semantic_prefilter(user_query)

        if not similarities:
            if fallback:
                logger.warning(f"No workflows matched, using fallback: {fallback}")
                return fallback
            workflows = self.registry.list_workflows()
            if workflows:
                default = workflows[0].name
                logger.warning(f"No workflows matched, using default: {default}")
                return default
            msg = "No workflows registered"
            raise ValueError(msg)

        # Get Top-K candidates
        top_candidates = [
            self.registry.get_workflow(name)
            for name, _ in similarities[: self.top_k]
            if self.registry.get_workflow(name) is not None
        ]

        if len(top_candidates) == 1:
            # Only one candidate, no need for LLM classification
            selected = top_candidates[0].name
            logger.info(
                f"Single candidate after pre-filtering: {selected} "
                f"(similarity: {similarities[0][1]:.3f})"
            )
            return selected

        # Phase 2: LLM classification
        decision = await self.llm_classify(user_query, top_candidates)

        # Validate decision (ensure selected workflow exists)
        if self.registry.get_workflow(decision.workflow_name):
            return decision.workflow_name
        logger.warning(
            f"LLM selected invalid workflow '{decision.workflow_name}', "
            f"falling back to first candidate: {top_candidates[0].name}"
        )
        return top_candidates[0].name

    def get_statistics(self) -> dict:
        """
        Get router statistics for monitoring.

        Returns:
            Dictionary with router configuration and index statistics
        """
        return {
            "registered_workflows": self.registry.workflow_count(),
            "indexed_workflows": len(self.example_vectors),
            "top_k": self.top_k,
            "embedding_dimension": (
                len(next(iter(self.example_vectors.values()))) if self.example_vectors else 0
            ),
        }
