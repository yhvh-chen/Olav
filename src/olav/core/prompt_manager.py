"""Prompt management system using LangChain PromptTemplate."""

import logging
from pathlib import Path
from typing import Any

import yaml
from langchain_core.prompts import PromptTemplate

logger = logging.getLogger(__name__)


class PromptManager:
    """Centralized prompt template manager with caching and hot reload."""

    def __init__(self, prompts_dir: str | Path | None = None) -> None:
        """Initialize prompt manager.

        Args:
            prompts_dir: Directory containing prompt YAML files (defaults to config.settings.Paths.PROMPTS_DIR)
        """
        if prompts_dir is None:
            from config.settings import Paths

            prompts_dir = Paths.PROMPTS_DIR
        self.prompts_dir = Path(prompts_dir)
        self._cache: dict[str, PromptTemplate] = {}

    def load_prompt(
        self,
        category: str,
        name: str,
        **kwargs: Any,
    ) -> str:
        """Load and render a prompt template.

        Args:
            category: Prompt category (agents/tools/rag/workflows/orchestrator)
                     Supports nested paths like "workflows/orchestrator"
            name: Prompt template name
            **kwargs: Variables to render in template

        Returns:
            Rendered prompt string

        Raises:
            FileNotFoundError: If prompt file doesn't exist
            ValueError: If required variables are missing
        """
        cache_key = f"{category}/{name}"

        # Load from cache or file
        if cache_key not in self._cache:
            # Support nested directory paths (e.g., "workflows/orchestrator")
            prompt_path = self.prompts_dir / category / f"{name}.yaml"
            if not prompt_path.exists():
                msg = f"Prompt file not found: {prompt_path}"
                raise FileNotFoundError(msg)

            # Parse YAML file with metadata structure
            with prompt_path.open(encoding="utf-8") as f:
                prompt_data = yaml.safe_load(f)

            # Extract template and input_variables from YAML structure
            if not isinstance(prompt_data, dict) or "template" not in prompt_data:
                msg = f"Invalid prompt format in {prompt_path}: missing 'template' field"
                raise ValueError(msg)

            template_str = prompt_data["template"]
            input_vars = prompt_data.get("input_variables", [])

            self._cache[cache_key] = PromptTemplate(
                template=template_str,
                input_variables=input_vars,
            )
            logger.debug(f"Loaded prompt template: {cache_key}")

        template = self._cache[cache_key]

        # Validate required variables
        missing = set(template.input_variables) - set(kwargs.keys())
        if missing:
            msg = f"Missing required variables for {cache_key}: {missing}"
            raise ValueError(msg)

        return template.format(**kwargs)

    def load_agent_prompt(self, agent_name: str, **context: Any) -> str:
        """Shortcut for loading agent system prompts.

        Args:
            agent_name: Name of the agent
            **context: Context variables for prompt

        Returns:
            Rendered agent system prompt
        """
        return self.load_prompt("agents", agent_name, **context)

    def load_tool_description(self, tool_name: str, **context: Any) -> str:
        """Shortcut for loading tool descriptions.

        Args:
            tool_name: Name of the tool
            **context: Context variables for description

        Returns:
            Rendered tool description
        """
        return self.load_prompt("tools", tool_name, **context)

    def reload(self) -> None:
        """Clear cache to force reload of all templates."""
        self._cache.clear()
        logger.info("Prompt cache cleared - all templates will reload")


# Global prompt manager instance
prompt_manager = PromptManager()
