"""OLAV Settings Configuration Manager.

This module manages OLAV configuration from agent_dir/settings.json.
Provides centralized access to all configuration options with validation.
"""

import json
from pathlib import Path
from typing import Any


class OlavSettings:
    """OLAV Settings Manager.

    Manages configuration from agent_dir/settings.json with defaults and validation.
    """

    DEFAULT_SETTINGS = {
        "diagnosis": {
            "requireApprovalForMicroAnalysis": True,
            "autoApproveIfConfidenceBelow": 0.5,
        },
        "execution": {
            "useTextFSM": True,
            "textFSMFallbackToRaw": True,
            "enableTokenStatistics": True,
        },
        "learning": {
            "autoSaveSolutions": False,
            "autoLearnAliases": False,
        },
        "subagents": {
            "enabled": True,
        },
    }

    def __init__(self, settings_path: Path | None = None, project_root: Path | None = None) -> None:
        """Initialize settings manager.

        Args:
            settings_path: Path to settings.json file
            project_root: Project root directory (defaults to cwd)
        """
        if project_root is None:
            project_root = Path.cwd()

        if settings_path is None:
            settings_path = project_root / ".olav" / "settings.json"

        self.settings_path = settings_path
        self.project_root = project_root
        self._settings = self._load_settings()

    def _load_settings(self) -> dict[str, Any]:
        """Load settings from file, merging with defaults.

        Returns:
            Merged settings dictionary
        """
        # Start with defaults
        settings = self.DEFAULT_SETTINGS.copy()

        # Load user settings if file exists
        if self.settings_path.exists():
            try:
                with open(self.settings_path, encoding="utf-8") as f:
                    user_settings = json.load(f)

                # Deep merge user settings with defaults
                settings = self._deep_merge(settings, user_settings)
            except (OSError, json.JSONDecodeError) as e:
                print(f"Warning: Failed to load settings from {self.settings_path}: {e}")
                print("Using default settings.")

        # Validate settings
        self._validate_settings(settings)

        return settings

    def _deep_merge(self, base: dict, update: dict) -> dict:
        """Deep merge two dictionaries.

        Args:
            base: Base dictionary
            update: Dictionary to merge into base

        Returns:
            Merged dictionary
        """
        result = base.copy()
        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _validate_settings(self, settings: dict[str, Any]) -> None:
        """Validate settings values.

        Args:
            settings: Settings dictionary to validate

        Raises:
            ValueError: If settings are invalid
        """
        # Validate diagnosis settings
        if "diagnosis" in settings:
            diagnosis = settings["diagnosis"]
            if "autoApproveIfConfidenceBelow" in diagnosis:
                confidence = diagnosis["autoApproveIfConfidenceBelow"]
                if not 0.0 <= confidence <= 1.0:
                    msg = (
                        "diagnosis.autoApproveIfConfidenceBelow must be "
                        f"between 0 and 1, got {confidence}"
                    )
                    raise ValueError(msg)

        # Validate execution settings
        if "execution" in settings:
            execution = settings["execution"]
            for bool_key in ["useTextFSM", "textFSMFallbackToRaw", "enableTokenStatistics"]:
                if bool_key in execution and not isinstance(execution[bool_key], bool):
                    raise ValueError(f"execution.{bool_key} must be a boolean")

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get a setting value by dot-separated path.

        Args:
            key_path: Dot-separated path (e.g., "diagnosis.requireApprovalForMicroAnalysis")
            default: Default value if key not found

        Returns:
            Setting value or default

        Examples:
            >>> settings.get("diagnosis.requireApprovalForMicroAnalysis")
            True
            >>> settings.get("execution.useTextFSM")
            True
        """
        keys = key_path.split(".")
        value = self._settings

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default

        return value

    def set(self, key_path: str, value: Any) -> None:
        """Set a setting value by dot-separated path.

        Args:
            key_path: Dot-separated path (e.g., "diagnosis.requireApprovalForMicroAnalysis")
            value: Value to set
        """
        keys = key_path.split(".")
        settings = self._settings

        # Navigate to parent
        for key in keys[:-1]:
            if key not in settings:
                settings[key] = {}
            settings = settings[key]

        # Set value
        settings[keys[-1]] = value

        # Validate
        self._validate_settings(self._settings)

    def save(self) -> None:
        """Save current settings to file."""
        # Ensure directory exists
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)

        # Write settings
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump(self._settings, f, indent=2, ensure_ascii=False)

    @property
    def diagnosis_require_approval(self) -> bool:
        """Get diagnosis approval requirement."""
        return self.get("diagnosis.requireApprovalForMicroAnalysis", True)

    @property
    def diagnosis_auto_approve_threshold(self) -> float:
        """Get auto-approval confidence threshold."""
        return self.get("diagnosis.autoApproveIfConfidenceBelow", 0.5)

    @property
    def execution_use_textfsm(self) -> bool:
        """Get TextFSM usage setting."""
        return self.get("execution.useTextFSM", True)

    @property
    def execution_textfsm_fallback(self) -> bool:
        """Get TextFSM fallback to raw text setting."""
        return self.get("execution.textFSMFallbackToRaw", True)

    @property
    def execution_enable_token_stats(self) -> bool:
        """Get token statistics tracking setting."""
        return self.get("execution.enableTokenStatistics", True)

    def __repr__(self) -> str:
        """String representation."""
        return f"OlavSettings(path={self.settings_path})"


# Global settings instance
_settings_instance: OlavSettings | None = None


def get_settings(project_root: Path | None = None) -> OlavSettings:
    """Get global settings instance (singleton pattern).

    Args:
        project_root: Project root directory

    Returns:
        OlavSettings instance
    """
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = OlavSettings(project_root=project_root)
    return _settings_instance


def reload_settings(project_root: Path | None = None) -> OlavSettings:
    """Reload settings from file.

    Args:
        project_root: Project root directory

    Returns:
        New OlavSettings instance
    """
    global _settings_instance
    _settings_instance = OlavSettings(project_root=project_root)
    return _settings_instance
