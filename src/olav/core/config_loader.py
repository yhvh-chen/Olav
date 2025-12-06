"""OLAV User Configuration Loader.

Loads user-facing configuration from olav.yaml with defaults fallback.
This is separate from config/settings.py which handles internal settings.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Default configuration values
_DEFAULTS = {
    "llm": {
        "provider": "ollama",
        "base_url": "http://127.0.0.1:11434",
        "model": "qwen3:30b",
        "temperature": 0.2,
        "max_tokens": 16000,
    },
    "thinking": {
        "enabled": True,
        "strategies": {
            "fast_path": False,  # FastPath is concise by default
            "deep_path": True,   # DeepPath can use extended thinking
            "batch": False,      # Batch processing is fast
        },
    },
    "query": {
        "max_age_hours": 72,  # Accept data up to 72 hours old
        "default_namespace": "default",
        "max_results": 1000,
    },
    "diagnosis": {
        "max_depth": 3,
        "max_parallel_queries": 5,
        "timeout_seconds": 120,
    },
    "safety": {
        "hitl_enabled": True,
        "dry_run_default": True,
        "allowed_write_operations": ["config_push", "netbox_sync"],
    },
    "answer": {
        "language": "zh-CN",  # Response language
        "include_raw_data": False,
        "max_table_rows": 50,
    },
    "prompt_overrides": {},  # Inline prompt overrides
}


class OlavConfig:
    """User configuration from olav.yaml with defaults fallback."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        """Initialize configuration.

        Args:
            config_path: Path to olav.yaml (defaults to config/olav.yaml)
        """
        if config_path is None:
            from config.settings import CONFIG_DIR
            config_path = CONFIG_DIR / "olav.yaml"

        self._path = Path(config_path)
        self._config: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load configuration from file with defaults fallback."""
        # Start with defaults
        self._config = _deep_copy(_DEFAULTS)

        # Override with user config if exists
        if self._path.exists():
            try:
                with self._path.open(encoding="utf-8") as f:
                    user_config = yaml.safe_load(f) or {}

                # Deep merge user config into defaults
                self._config = _deep_merge(self._config, user_config)
                logger.info(f"Loaded user config from {self._path}")
            except Exception as e:
                logger.warning(f"Failed to load {self._path}: {e}, using defaults")
        else:
            logger.debug(f"No user config at {self._path}, using defaults")

    def reload(self) -> None:
        """Reload configuration from file."""
        self._load()

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with dot notation.

        Args:
            key: Configuration key (e.g., "llm.model", "thinking.enabled")
            default: Default value if key not found

        Returns:
            Configuration value

        Example:
            config.get("llm.model")  # "qwen3:30b"
            config.get("thinking.strategies.fast_path")  # False
        """
        parts = key.split(".")
        value = self._config

        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default

        return value

    def __getitem__(self, key: str) -> Any:
        """Get configuration section.

        Args:
            key: Top-level section key

        Returns:
            Configuration section dict
        """
        return self._config.get(key, {})

    def to_dict(self) -> dict[str, Any]:
        """Get full configuration as dict."""
        return _deep_copy(self._config)

    @property
    def llm(self) -> dict[str, Any]:
        """LLM configuration section."""
        return self._config.get("llm", {})

    @property
    def thinking(self) -> dict[str, Any]:
        """Thinking mode configuration."""
        return self._config.get("thinking", {})

    @property
    def query(self) -> dict[str, Any]:
        """Query behavior configuration."""
        return self._config.get("query", {})

    @property
    def safety(self) -> dict[str, Any]:
        """Safety/HITL configuration."""
        return self._config.get("safety", {})

    @property
    def answer(self) -> dict[str, Any]:
        """Answer formatting configuration."""
        return self._config.get("answer", {})

    def is_thinking_enabled(self, strategy: str = "default") -> bool:
        """Check if thinking is enabled for a strategy.

        Args:
            strategy: Strategy name (fast_path, deep_path, batch)

        Returns:
            True if thinking enabled for this strategy
        """
        thinking = self.thinking
        strategies = thinking.get("strategies", {})

        # Check strategy-specific setting first
        if strategy in strategies:
            return strategies[strategy]

        # Fall back to global setting
        return thinking.get("enabled", True)


def _deep_copy(d: dict) -> dict:
    """Deep copy a dict (simple implementation for config)."""
    import copy
    return copy.deepcopy(d)


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base dict.

    Args:
        base: Base dictionary
        override: Override dictionary

    Returns:
        Merged dictionary (modifies base)
    """
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


# Global config instance (lazy loaded)
_config: OlavConfig | None = None


def get_config() -> OlavConfig:
    """Get global configuration instance.

    Returns:
        OlavConfig singleton
    """
    global _config
    if _config is None:
        _config = OlavConfig()
    return _config


def reload_config() -> None:
    """Reload global configuration from file."""
    global _config
    if _config is not None:
        _config.reload()
