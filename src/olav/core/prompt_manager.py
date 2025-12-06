"""Prompt management system using LangChain PromptTemplate.

Supports two-layer prompt resolution:
1. _defaults/ - Built-in English prompts
2. overrides/ - User customizations (optional)

Prompt lookup order:
1. overrides/{name}.yaml (if exists)
2. _defaults/{name}.yaml

Example:
    prompt_manager = PromptManager()
    prompt = prompt_manager.load("answer_formatting", user_query="...", data_json="...")
"""

import logging
from pathlib import Path
from typing import Any

import yaml
from langchain_core.prompts import PromptTemplate

logger = logging.getLogger(__name__)


class PromptManager:
    """Centralized prompt template manager with caching and two-layer resolution.

    Features:
    - Two-layer lookup: overrides/ takes precedence over _defaults/
    - Template caching for performance
    - Support for thinking mode prefix injection
    - Legacy compatibility with category-based paths
    """

    def __init__(
        self,
        prompts_dir: str | Path | None = None,
        olav_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize prompt manager.

        Args:
            prompts_dir: Directory containing prompt YAML files
                        (defaults to config.settings.Paths.PROMPTS_DIR)
            olav_config: User configuration from olav.yaml (optional)
        """
        if prompts_dir is None:
            from config.settings import Paths

            prompts_dir = Paths.PROMPTS_DIR
        self.prompts_dir = Path(prompts_dir)
        self._defaults_dir = self.prompts_dir / "_defaults"
        self._overrides_dir = self.prompts_dir / "overrides"
        self._cache: dict[str, PromptTemplate] = {}
        self._raw_cache: dict[str, dict] = {}  # Cache for raw YAML data
        self._config = olav_config or {}

    def _resolve_prompt_path(self, name: str) -> Path:
        """Resolve prompt file path with two-layer lookup.

        Args:
            name: Prompt name (without .yaml extension)

        Returns:
            Path to the prompt file

        Raises:
            FileNotFoundError: If prompt not found in either layer
        """
        # Priority 1: overrides/
        override_path = self._overrides_dir / f"{name}.yaml"
        if override_path.exists():
            logger.debug(f"Using override prompt: {name}")
            return override_path

        # Priority 2: _defaults/
        default_path = self._defaults_dir / f"{name}.yaml"
        if default_path.exists():
            return default_path

        msg = f"Prompt not found: {name} (checked overrides/ and _defaults/)"
        raise FileNotFoundError(msg)

    def load(
        self,
        name: str,
        *,
        thinking: bool | None = None,
        **kwargs: Any,
    ) -> str:
        """Load and render a prompt template (new API).

        Args:
            name: Prompt name (e.g., "answer_formatting")
            thinking: Override thinking mode (None = use config default)
            **kwargs: Variables to render in template

        Returns:
            Rendered prompt string, optionally with thinking prefix
        """
        # Check inline override in config first
        inline_override = self._config.get("prompt_overrides", {}).get(name)
        if inline_override:
            template = PromptTemplate(
                template=inline_override,
                input_variables=list(kwargs.keys()),
            )
            return self._apply_thinking_prefix(template.format(**kwargs), thinking, name)

        # Load from file with caching
        if name not in self._cache:
            prompt_path = self._resolve_prompt_path(name)
            prompt_data = self._load_yaml(prompt_path)

            template_str = prompt_data["template"]
            input_vars = prompt_data.get("input_variables", [])

            self._cache[name] = PromptTemplate(
                template=template_str,
                input_variables=input_vars,
            )
            self._raw_cache[name] = prompt_data
            logger.debug(f"Loaded prompt: {name} from {prompt_path}")

        template = self._cache[name]

        # Validate required variables
        missing = set(template.input_variables) - set(kwargs.keys())
        if missing:
            msg = f"Missing required variables for {name}: {missing}"
            raise ValueError(msg)

        rendered = template.format(**kwargs)
        return self._apply_thinking_prefix(rendered, thinking, name)

    def _load_yaml(self, path: Path) -> dict:
        """Load and validate YAML prompt file."""
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict) or "template" not in data:
            msg = f"Invalid prompt format in {path}: missing 'template' field"
            raise ValueError(msg)

        return data

    def _apply_thinking_prefix(
        self,
        prompt: str,
        thinking: bool | None,
        prompt_name: str,
    ) -> str:
        """Apply thinking mode prefix based on config and prompt metadata.

        NOTE: This is a fallback mechanism. The preferred approach is using
        the native Ollama `think` parameter via OllamaChat(think=False).
        The /nothink prefix is kept for backward compatibility.

        Args:
            prompt: Rendered prompt string
            thinking: Explicit thinking override (None = use config)
            prompt_name: Name of prompt (for metadata lookup)

        Returns:
            Prompt with /nothink prefix if thinking is disabled
        """
        # Check if prompt supports thinking
        meta = self._raw_cache.get(prompt_name, {}).get("_meta", {})
        if not meta.get("supports_thinking", True):
            return prompt  # Prompt doesn't use thinking

        # Determine thinking mode
        if thinking is None:
            # Use config default for strategy
            strategy = meta.get("strategy", "default")
            thinking_config = self._config.get("thinking", {})
            strategies = thinking_config.get("strategies", {})
            thinking = strategies.get(strategy, thinking_config.get("enabled", True))

        # Add /nothink prefix if thinking disabled
        if not thinking:
            return f"/nothink\n{prompt}"

        return prompt

    # ========== Legacy API (backward compatibility) ==========

    def load_prompt(
        self,
        category: str,
        name: str,
        **kwargs: Any,
    ) -> str:
        """Load and render a prompt template (legacy API).

        DEPRECATED: Use load() instead for new prompts.

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
            prompt_data = self._load_yaml(prompt_path)
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
        """Shortcut for loading agent system prompts (legacy API).

        DEPRECATED: Use load() instead.

        Args:
            agent_name: Name of the agent
            **context: Context variables for prompt

        Returns:
            Rendered agent system prompt
        """
        return self.load_prompt("agents", agent_name, **context)

    def load_tool_description(self, tool_name: str, **context: Any) -> str:
        """Shortcut for loading tool descriptions (legacy API).

        DEPRECATED: Use load() instead.

        Args:
            tool_name: Name of the tool
            **context: Context variables for description

        Returns:
            Rendered tool description
        """
        return self.load_prompt("tools", tool_name, **context)

    def load_tool_capability_guide(self, tool_name: str) -> str:
        """Load tool capability guide (legacy API).

        DEPRECATED: Use load() instead.

        Args:
            tool_name: Name of the tool (e.g., "suzieq")

        Returns:
            Capability guide content, or empty string if not found
        """
        try:
            return self.load_prompt("tools", f"{tool_name}_capability_guide")
        except FileNotFoundError:
            logger.debug(f"No capability guide found for tool: {tool_name}")
            return ""

    def load_raw_template(self, category: str, name: str) -> str:
        """Load raw template string without PromptTemplate parsing (legacy API).

        DEPRECATED: Use load_raw() instead.

        Use this for templates containing JSON or other content with {}
        that would conflict with LangChain's variable syntax.

        Args:
            category: Prompt category path (e.g., "strategies/fast_path")
            name: Template name without .yaml extension

        Returns:
            Raw template string (caller must handle variable substitution)

        Raises:
            FileNotFoundError: If prompt file doesn't exist
        """
        prompt_path = self.prompts_dir / category / f"{name}.yaml"
        if not prompt_path.exists():
            msg = f"Prompt file not found: {prompt_path}"
            raise FileNotFoundError(msg)

        prompt_data = self._load_yaml(prompt_path)
        return prompt_data["template"]

    def load_raw(self, name: str) -> str:
        """Load raw template without variable substitution (new API).

        Args:
            name: Prompt name (e.g., "answer_formatting")

        Returns:
            Raw template string
        """
        prompt_path = self._resolve_prompt_path(name)
        prompt_data = self._load_yaml(prompt_path)
        return prompt_data["template"]

    # ========== Utilities ==========

    def reload(self) -> None:
        """Clear cache to force reload of all templates."""
        self._cache.clear()
        self._raw_cache.clear()
        logger.info("Prompt cache cleared - all templates will reload")

    def list_prompts(self) -> dict[str, list[str]]:
        """List all available prompts.

        Returns:
            Dict with 'defaults' and 'overrides' lists
        """
        result = {"defaults": [], "overrides": []}

        if self._defaults_dir.exists():
            result["defaults"] = [
                p.stem for p in self._defaults_dir.glob("*.yaml")
                if not p.stem.startswith("_")
            ]

        if self._overrides_dir.exists():
            result["overrides"] = [
                p.stem for p in self._overrides_dir.glob("*.yaml")
                if not p.stem.startswith("_")
            ]

        return result

    def set_config(self, config: dict[str, Any]) -> None:
        """Update configuration at runtime.

        Args:
            config: New configuration dict (from olav.yaml)
        """
        self._config = config
        self.reload()  # Clear cache to apply new settings


def _create_prompt_manager() -> PromptManager:
    """Create prompt manager with user configuration.

    Loads olav.yaml if available for thinking mode settings.
    """
    try:
        from src.olav.core.config_loader import get_config
        config = get_config().to_dict()
    except Exception:
        # Fallback if config loader fails
        config = {}

    return PromptManager(olav_config=config)


# Global prompt manager instance
prompt_manager = _create_prompt_manager()
