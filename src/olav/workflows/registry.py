"""
Workflow Registry - Plugin-based workflow registration system.

This module implements a decorator-based registry pattern for workflows,
enabling zero-invasive extensibility. New workflows can be added by simply
decorating the workflow class with @WorkflowRegistry.register.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

logger = logging.getLogger(__name__)


@dataclass
class WorkflowMetadata:
    """
    Metadata for a registered workflow.

    Attributes:
        name: Unique workflow identifier (e.g., "network_diagnosis")
        description: Human-readable description of workflow capabilities
        examples: Sample queries for semantic matching (used in intent router)
        triggers: Regex patterns that trigger this workflow (optional)
        class_ref: Reference to the workflow class implementation
    """

    name: str
    description: str
    examples: list[str]
    triggers: list[str] | None = None
    class_ref: type | None = None


class WorkflowRegistry:
    """
    Central registry for workflow plugins.

    Workflows self-register using the @register decorator. The Dynamic Intent
    Router queries this registry to discover available workflows and their
    capabilities for semantic routing.

    Example:
        >>> @WorkflowRegistry.register(
        ...     name="network_diagnosis",
        ...     description="Network state queries, BGP/OSPF diagnostics",
        ...     examples=[
        ...         "查询 R1 的 BGP 邻居状态",
        ...         "为什么 Switch-A 和 Switch-B 之间丢包？",
        ...     ],
        ...     triggers=[r"BGP", r"OSPF", r"接口.*状态"]
        ... )
        ... class NetworkDiagnosisWorkflow(BaseWorkflow):
        ...     pass
    """

    _workflows: ClassVar[dict[str, WorkflowMetadata]] = {}

    @classmethod
    def register(
        cls,
        name: str,
        description: str,
        examples: list[str],
        triggers: list[str] | None = None,
    ) -> Callable:
        """
        Decorator to register a workflow class.

        Args:
            name: Unique workflow identifier
            description: Workflow capabilities description
            examples: Sample queries for semantic matching
            triggers: Optional regex patterns for keyword-based routing

        Returns:
            Decorator function that registers the workflow class

        Raises:
            ValueError: If workflow name already registered
        """

        def decorator(workflow_class: type) -> type:
            if name in cls._workflows:
                msg = (
                    f"Workflow '{name}' already registered. "
                    f"Existing: {cls._workflows[name].class_ref}, "
                    f"New: {workflow_class}"
                )
                raise ValueError(msg)

            metadata = WorkflowMetadata(
                name=name,
                description=description,
                examples=examples,
                triggers=triggers,
                class_ref=workflow_class,
            )

            cls._workflows[name] = metadata
            logger.info(
                f"Registered workflow: {name} ({workflow_class.__name__}) "
                f"with {len(examples)} examples"
            )

            return workflow_class

        return decorator

    @classmethod
    def get_workflow(cls, name: str) -> WorkflowMetadata | None:
        """
        Retrieve workflow metadata by name.

        Args:
            name: Workflow identifier

        Returns:
            WorkflowMetadata if found, None otherwise
        """
        return cls._workflows.get(name)

    @classmethod
    def list_workflows(cls) -> list[WorkflowMetadata]:
        """
        Get all registered workflows.

        Returns:
            List of all workflow metadata objects
        """
        return list(cls._workflows.values())

    @classmethod
    def match_triggers(cls, query: str) -> list[str]:
        """
        Find workflows matching trigger patterns in query.

        This provides fast keyword-based routing before semantic analysis.

        Args:
            query: User query string

        Returns:
            List of workflow names with matching trigger patterns
        """
        matched = []

        for name, metadata in cls._workflows.items():
            if metadata.triggers:
                for pattern in metadata.triggers:
                    if re.search(pattern, query, re.IGNORECASE):
                        matched.append(name)
                        break  # One match is enough per workflow

        return matched

    @classmethod
    def clear(cls) -> None:
        """
        Clear all registered workflows.

        This is primarily for testing purposes to reset the registry state.
        """
        cls._workflows.clear()
        logger.debug("Cleared workflow registry")

    @classmethod
    def workflow_count(cls) -> int:
        """
        Get number of registered workflows.

        Returns:
            Count of registered workflows
        """
        return len(cls._workflows)
