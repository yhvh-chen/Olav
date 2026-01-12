"""Subagent Manager - Manages specialized network analysis subagents.

This module provides integration with DeepAgents' SubAgentMiddleware to enable
specialized subagents for macro and micro network analysis.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deepagents.middleware.subagents import SubAgentMiddleware

try:
    from deepagents.middleware.subagents import SubAgentMiddleware

    DEEPAGENTS_AVAILABLE = True
except ImportError:
    DEEPAGENTS_AVAILABLE = False
    SubAgentMiddleware = None  # type: ignore[misc, assignment]

from langchain_core.tools import BaseTool

from olav.core.llm import LLMFactory

# Import from subagent_configs instead of agent to avoid circular import
from olav.core.subagent_configs import get_macro_analyzer, get_micro_analyzer


def get_subagent_middleware(
    tools: list[BaseTool],
    default_model: object | None = None,
) -> object:  # noqa: ANN401
    """Create and configure SubAgentMiddleware with OLAV's specialized analyzers.

    This middleware enables the main agent to delegate complex analysis tasks
    to specialized subagents:
    - general-purpose (macro): Topology, paths, end-to-end connectivity
    - general-purpose (micro): TCP/IP layer-by-layer troubleshooting

    Note: DeepAgents currently only supports 'general-purpose' subagent type.
    We configure specialized prompts to differentiate roles.

    Args:
        tools: List of tools available to subagents
        default_model: Default LLM model for subagents (uses LLMFactory if None)

    Returns:
        Configured SubAgentMiddleware instance, or None if DeepAgents not available
    """
    if not DEEPAGENTS_AVAILABLE or SubAgentMiddleware is None:
        return None

    if default_model is None:
        default_model = LLMFactory.get_chat_model()

    # Define subagents using official DeepAgents API format
    # See: https://github.com/langchain-ai/deepagents
    subagents: list[dict[str, Any]] = [  # noqa: ANN401
        {
            **get_macro_analyzer(tools=tools),
            "model": default_model,
        },
        {
            **get_micro_analyzer(tools=tools),
            "model": default_model,
        },
    ]

    # Create middleware with our analyzers
    middleware = SubAgentMiddleware(
        subagents=subagents,  # type: ignore[arg-type]
        default_model=default_model,  # type: ignore[arg-type]
    )

    return middleware


def get_available_subagents() -> dict[str, dict[str, str]]:
    """Get descriptions of available subagents for tool documentation.

    Returns:
        Dictionary mapping subagent names to their descriptions

    Note: DeepAgents framework currently only registers these as 'general-purpose'
    type, but they are invoked with specialized prompts based on intent.
    """
    return {
        "macro-analyzer": {
            "name": "macro-analyzer",
            "description": "Macro analysis: topology, paths, end-to-end connectivity",
            "use_case": (
                "Use for: identifying fault domains, tracing data paths, "
                "checking end-to-end connectivity"
            ),
        },
        "micro-analyzer": {
            "name": "micro-analyzer",
            "description": "Micro analysis: TCP/IP layer-by-layer troubleshooting",
            "use_case": (
                "Use for: physical/data link/network/transport layer issues on specific devices"
            ),
        },
    }


def format_subagent_descriptions() -> str:
    """Format subagent descriptions for inclusion in system prompt.

    Returns:
        Formatted string describing available subagents
    """
    agents = get_available_subagents()

    lines = [
        "## Available Subagents",
        "",
        "You can delegate complex analysis tasks to specialized subagents:",
        "",
    ]

    for name, info in agents.items():
        lines.append(f"### {name}")
        lines.append(f"**Description**: {info['description']}")
        lines.append(f"**When to use**: {info['use_case']}")
        lines.append("")

    return "\n".join(lines)
