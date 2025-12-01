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

Refactored: Uses LangChain InMemoryVectorStore instead of sklearn cosine_similarity.

Usage:
    router = DynamicIntentRouter(llm_factory, embeddings_factory)
    await router.build_index()  # One-time at startup
    workflow_name = await router.route("查询 R1 的 BGP 状态")
"""

import logging
from typing import Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.vectorstores import InMemoryVectorStore
from pydantic import BaseModel, Field

from olav.core.json_utils import robust_structured_output
from olav.core.prompt_manager import prompt_manager
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
        vector_store: InMemoryVectorStore for semantic search
        indexed: Whether the index has been built
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
        self.vector_store: InMemoryVectorStore | None = None
        self._indexed = False
        self._workflow_count = 0
        self.registry = WorkflowRegistry

        logger.info(
            f"Initialized DynamicIntentRouter with {top_k} candidates, "
            f"LLM: {type(llm).__name__}, Embeddings: {type(embeddings).__name__}"
        )

    async def build_index(self) -> None:
        """
        Build semantic index for all registered workflows.

        This should be called once at startup. Creates documents from workflow
        examples and indexes them in InMemoryVectorStore.

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

        # Create InMemoryVectorStore
        self.vector_store = InMemoryVectorStore(embedding=self.embeddings)

        # Build documents from workflow examples
        documents: list[Document] = []
        for metadata in workflows:
            if not metadata.examples:
                logger.warning(
                    f"Workflow '{metadata.name}' has no examples, using description for embedding"
                )
                texts = [metadata.description]
            else:
                texts = metadata.examples

            # Create a document for each example
            for text in texts:
                doc = Document(
                    page_content=text,
                    metadata={"workflow": metadata.name, "description": metadata.description},
                )
                documents.append(doc)

            logger.debug(f"Created {len(texts)} documents for workflow '{metadata.name}'")

        # Add all documents to vector store
        await self.vector_store.aadd_documents(documents)
        self._indexed = True
        self._workflow_count = len(workflows)

        logger.info(f"Semantic index built successfully. Total documents indexed: {len(documents)}")

    async def semantic_prefilter(self, query: str) -> list[tuple[str, float]]:
        """
        Phase 1: Semantic pre-filtering using InMemoryVectorStore.

        Args:
            query: User query string

        Returns:
            List of (workflow_name, similarity_score) tuples, sorted by score

        Raises:
            RuntimeError: If semantic index not built (call build_index first)
        """
        if not self._indexed or self.vector_store is None:
            msg = "Semantic index not built. Call build_index() first."
            raise RuntimeError(msg)

        # Use vector store similarity search with scores
        # Get more results than top_k to aggregate by workflow
        results = await self.vector_store.asimilarity_search_with_score(
            query,
            k=self.top_k * 3,  # Get extra to aggregate
        )

        # Aggregate scores by workflow (take max score for each workflow)
        workflow_scores: dict[str, float] = {}
        for doc, score in results:
            workflow = doc.metadata.get("workflow", "unknown")
            # InMemoryVectorStore returns distance, not similarity
            # Lower distance = more similar, so we negate or invert
            # Note: The score semantics depend on the implementation
            # For cosine similarity, 0 = identical, so we convert
            similarity = 1.0 - score if score <= 1.0 else 1.0 / (1.0 + score)
            if workflow not in workflow_scores or similarity > workflow_scores[workflow]:
                workflow_scores[workflow] = similarity

        # Sort by similarity (descending)
        similarities = sorted(workflow_scores.items(), key=lambda x: x[1], reverse=True)

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

        prompt = prompt_manager.load_prompt(
            "agents",
            "intent_router",
            query=query,
            candidates_desc=candidates_desc,
        )

        # Use robust_structured_output for reliable JSON parsing
        try:
            decision = await robust_structured_output(
                llm=self.llm,
                output_class=RouteDecision,
                prompt=prompt,
            )
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
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

    def get_statistics(self) -> dict[str, Any]:
        """
        Get router statistics for monitoring.

        Returns:
            Dictionary with router configuration and index statistics
        """
        return {
            "registered_workflows": self.registry.workflow_count(),
            "indexed_workflows": self._workflow_count,
            "indexed": self._indexed,
            "top_k": self.top_k,
        }
