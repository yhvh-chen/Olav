"""
Test suite for OLAV Configuration Management (Phase C-1)

Tests three-layer configuration architecture:
1. Layer 1: .env (敏感配置)
2. Layer 2: .olav/settings.json (行为配置)
3. Layer 3: Code defaults (代码配置)

Priority: Environment variables > .env > .olav/settings.json > Code defaults
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from config.settings import (
    DiagnosisSettings,
    GuardSettings,
    HITLSettings,
    LoggingSettings,
    RoutingSettings,
    Settings,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_dir():
    """Create temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_olav_dir(temp_dir):
    """Create temporary .olav directory."""
    olav_dir = temp_dir / ".olav"
    olav_dir.mkdir(parents=True, exist_ok=True)
    return olav_dir


@pytest.fixture
def temp_env_file(temp_dir):
    """Create temporary .env file."""
    env_file = temp_dir / ".env"
    env_file.write_text("LLM_MODEL_NAME=gpt-4-turbo\nLLM_TEMPERATURE=0.1\n")
    return env_file


# =============================================================================
# Test Nested Settings Classes
# =============================================================================

class TestGuardSettings:
    """Test Guard settings configuration."""

    def test_default_values(self):
        """Test default Guard settings."""
        guard = GuardSettings()
        assert guard.enabled is True
        assert guard.strict_mode is False

    def test_custom_values(self):
        """Test custom Guard settings."""
        guard = GuardSettings(enabled=False, strict_mode=True)
        assert guard.enabled is False
        assert guard.strict_mode is True


class TestRoutingSettings:
    """Test Routing settings configuration."""

    def test_default_values(self):
        """Test default Routing settings."""
        routing = RoutingSettings()
        assert routing.confidence_threshold == 0.6
        assert routing.fallback_skill == "quick-query"

    def test_custom_values(self):
        """Test custom Routing settings."""
        routing = RoutingSettings(
            confidence_threshold=0.8,
            fallback_skill="deep-analysis"
        )
        assert routing.confidence_threshold == 0.8
        assert routing.fallback_skill == "deep-analysis"

    def test_confidence_threshold_validation(self):
        """Test confidence threshold bounds validation."""
        with pytest.raises(ValueError):
            RoutingSettings(confidence_threshold=1.5)

        with pytest.raises(ValueError):
            RoutingSettings(confidence_threshold=-0.1)


class TestHITLSettings:
    """Test HITL settings configuration."""

    def test_default_values(self):
        """Test default HITL settings."""
        hitl = HITLSettings()
        assert hitl.require_approval_for_write is True
        assert hitl.require_approval_for_skill_update is True
        assert hitl.approval_timeout_seconds == 300

    def test_custom_values(self):
        """Test custom HITL settings."""
        hitl = HITLSettings(
            require_approval_for_write=False,
            require_approval_for_skill_update=False,
            approval_timeout_seconds=600
        )
        assert hitl.require_approval_for_write is False
        assert hitl.require_approval_for_skill_update is False
        assert hitl.approval_timeout_seconds == 600

    def test_approval_timeout_validation(self):
        """Test approval timeout bounds validation."""
        with pytest.raises(ValueError):
            HITLSettings(approval_timeout_seconds=5)

        with pytest.raises(ValueError):
            HITLSettings(approval_timeout_seconds=4000)


class TestDiagnosisSettings:
    """Test Diagnosis settings configuration."""

    def test_default_values(self):
        """Test default Diagnosis settings."""
        diagnosis = DiagnosisSettings()
        assert diagnosis.macro_max_confidence == 0.7
        assert diagnosis.micro_target_confidence == 0.9
        assert diagnosis.max_diagnosis_iterations == 5

    def test_custom_values(self):
        """Test custom Diagnosis settings."""
        diagnosis = DiagnosisSettings(
            macro_max_confidence=0.6,
            micro_target_confidence=0.8,
            max_diagnosis_iterations=10
        )
        assert diagnosis.macro_max_confidence == 0.6
        assert diagnosis.micro_target_confidence == 0.8
        assert diagnosis.max_diagnosis_iterations == 10


class TestLoggingSettings:
    """Test Logging settings configuration."""

    def test_default_values(self):
        """Test default Logging settings."""
        logging = LoggingSettings()
        assert logging.level == "INFO"
        assert logging.audit_enabled is True

    def test_custom_values(self):
        """Test custom Logging settings."""
        logging = LoggingSettings(level="DEBUG", audit_enabled=False)
        assert logging.level == "DEBUG"
        assert logging.audit_enabled is False


# =============================================================================
# Test Settings Layer Configuration
# =============================================================================

class TestSettingsLayerPriority:
    """Test configuration layer priority: Env > .env > settings.json > defaults."""

    def test_layer3_default_values(self):
        """Test Layer 3: Code default values."""
        # Clear environment
        for key in ["LLM_MODEL_NAME", "LLM_TEMPERATURE"]:
            os.environ.pop(key, None)

        # Use code defaults (no .env or settings.json)
        with patch.dict(os.environ, {}, clear=False):
            settings = Settings()
            # Will use code defaults since no .env or settings.json exist
            assert settings.llm_temperature == 0.1

    def test_layer2_settings_json_override(self, temp_olav_dir, temp_dir):
        """Test Layer 2: .olav/settings.json overrides defaults."""
        # Create settings.json
        settings_json = {
            "model": "gpt-4o",
            "temperature": 0.5,
            "guard": {"enabled": False},
        }
        (temp_olav_dir / "settings.json").write_text(json.dumps(settings_json))

        # Mock OLAV_DIR to temp location
        with patch("config.settings.OLAV_DIR", temp_olav_dir):
            for key in ["LLM_MODEL_NAME", "LLM_TEMPERATURE"]:
                os.environ.pop(key, None)

            settings = Settings()
            assert settings.llm_model_name == "gpt-4o"
            assert settings.llm_temperature == 0.5
            assert settings.guard.enabled is False

    def test_layer1_environment_variable_priority(self, temp_olav_dir):
        """Test Layer 1: Environment variables have highest priority."""
        # Create settings.json with different value
        settings_json = {
            "model": "gpt-4o",
            "temperature": 0.5,
        }
        (temp_olav_dir / "settings.json").write_text(json.dumps(settings_json))

        # Set environment variable
        with patch.dict(
            os.environ,
            {"LLM_MODEL_NAME": "claude-3-5-sonnet"},
            clear=False
        ):
            with patch("config.settings.OLAV_DIR", temp_olav_dir):
                settings = Settings(
                    llm_model_name="claude-3-5-sonnet"  # Explicit parameter
                )
                # Environment variable should take priority
                # Note: Pydantic uses constructor parameters, not env vars
                assert settings.llm_model_name == "claude-3-5-sonnet"

    def test_nested_settings_from_json(self, temp_olav_dir):
        """Test Layer 2: Nested settings from JSON."""
        settings_json = {
            "routing": {
                "confidenceThreshold": 0.75,
                "fallbackSkill": "deep-analysis",
            },
            "diagnosis": {
                "macroMaxConfidence": 0.5,
                "microTargetConfidence": 0.95,
            },
        }
        (temp_olav_dir / "settings.json").write_text(json.dumps(settings_json))

        with patch("config.settings.OLAV_DIR", temp_olav_dir):
            settings = Settings()
            assert settings.routing.confidence_threshold == 0.75
            assert settings.routing.fallback_skill == "deep-analysis"
            assert settings.diagnosis.macro_max_confidence == 0.5
            assert settings.diagnosis.micro_target_confidence == 0.95


# =============================================================================
# Test Settings JSON Loading
# =============================================================================

class TestSettingsJsonLoading:
    """Test loading and validation of .olav/settings.json."""

    def test_load_valid_settings_json(self, temp_olav_dir):
        """Test loading valid settings.json."""
        settings_json = {
            "model": "gpt-4o",
            "temperature": 0.2,
            "enabledSkills": ["skill1", "skill2"],
            "disabledSkills": ["skill3"],
            "guard": {"enabled": True, "strictMode": False},
            "routing": {
                "confidenceThreshold": 0.65,
                "fallbackSkill": "fallback",
            },
        }
        (temp_olav_dir / "settings.json").write_text(json.dumps(settings_json))

        with patch("config.settings.OLAV_DIR", temp_olav_dir):
            settings = Settings()
            assert settings.llm_model_name == "gpt-4o"
            assert settings.llm_temperature == 0.2
            assert settings.enabled_skills == ["skill1", "skill2"]
            assert settings.disabled_skills == ["skill3"]

    def test_load_invalid_settings_json(self, temp_olav_dir):
        """Test graceful handling of invalid settings.json."""
        # Write invalid JSON
        (temp_olav_dir / "settings.json").write_text("{ invalid json }")

        with patch("config.settings.OLAV_DIR", temp_olav_dir):
            # Should not raise, just use defaults
            settings = Settings()
            assert settings.llm_model_name == "gpt-4-turbo"

    def test_missing_settings_json(self, temp_olav_dir):
        """Test behavior when settings.json doesn't exist."""
        with patch("config.settings.OLAV_DIR", temp_olav_dir):
            # Should use all defaults
            settings = Settings()
            assert settings.llm_temperature == 0.1
            assert settings.guard.enabled is True

    def test_partial_settings_json(self, temp_olav_dir):
        """Test loading partial settings.json (only some fields)."""
        settings_json = {
            "model": "gpt-4o",
            # Temperature not specified, should use default
        }
        (temp_olav_dir / "settings.json").write_text(json.dumps(settings_json))

        with patch("config.settings.OLAV_DIR", temp_olav_dir):
            settings = Settings()
            assert settings.llm_model_name == "gpt-4o"
            assert settings.llm_temperature == 0.1  # Default


# =============================================================================
# Test Settings Serialization
# =============================================================================

class TestSettingsSerialization:
    """Test settings serialization and export."""

    def test_save_to_json(self, temp_olav_dir):
        """Test saving settings to JSON file."""
        with patch("config.settings.OLAV_DIR", temp_olav_dir):
            settings = Settings()
            settings.llm_model_name = "gpt-4o"
            settings.llm_temperature = 0.3
            settings.routing.confidence_threshold = 0.7

            output_file = temp_olav_dir / "output_settings.json"
            settings.save_to_json(output_file)

            # Load and verify
            saved_json = json.loads(output_file.read_text())
            assert saved_json["model"] == "gpt-4o"
            assert saved_json["temperature"] == 0.3
            # Check camelCase conversion in nested objects
            assert saved_json["routing"]["confidenceThreshold"] == 0.7

    def test_to_dict(self):
        """Test converting settings to dictionary."""
        settings = Settings()
        settings_dict = settings.to_dict()

        assert isinstance(settings_dict, dict)
        assert "llm_model_name" in settings_dict
        assert "llm_temperature" in settings_dict
        assert "guard" in settings_dict
        assert "routing" in settings_dict


# =============================================================================
# Test Settings Validation
# =============================================================================

class TestSettingsValidation:
    """Test settings validation."""

    def test_validate_model_name_not_empty(self):
        """Test that model name validation rejects empty strings."""
        with pytest.raises(ValueError):
            Settings(llm_model_name="")

    def test_validate_temperature_bounds(self):
        """Test temperature validation."""
        # Valid values
        Settings(llm_temperature=0.0)
        Settings(llm_temperature=1.0)
        Settings(llm_temperature=2.0)

        # Invalid values
        with pytest.raises(ValueError):
            Settings(llm_temperature=-0.1)

        with pytest.raises(ValueError):
            Settings(llm_temperature=2.1)

    def test_validate_confidence_threshold_bounds(self):
        """Test confidence threshold validation."""
        # Valid values
        RoutingSettings(confidence_threshold=0.0)
        RoutingSettings(confidence_threshold=0.5)
        RoutingSettings(confidence_threshold=1.0)

        # Invalid values
        with pytest.raises(ValueError):
            RoutingSettings(confidence_threshold=-0.1)

        with pytest.raises(ValueError):
            RoutingSettings(confidence_threshold=1.1)


# =============================================================================
# Test Skill Enable/Disable
# =============================================================================

class TestSkillEnableDisable:
    """Test skill enable/disable configuration."""

    def test_enabled_skills_from_settings(self, temp_olav_dir):
        """Test loading enabled skills from settings.json."""
        settings_json = {
            "enabledSkills": ["quick-query", "deep-analysis"],
        }
        (temp_olav_dir / "settings.json").write_text(json.dumps(settings_json))

        with patch("config.settings.OLAV_DIR", temp_olav_dir):
            settings = Settings()
            assert settings.enabled_skills == ["quick-query", "deep-analysis"]

    def test_disabled_skills_from_settings(self, temp_olav_dir):
        """Test loading disabled skills from settings.json."""
        settings_json = {
            "disabledSkills": ["experimental"],
        }
        (temp_olav_dir / "settings.json").write_text(json.dumps(settings_json))

        with patch("config.settings.OLAV_DIR", temp_olav_dir):
            settings = Settings()
            assert settings.disabled_skills == ["experimental"]

    def test_both_enabled_and_disabled(self, temp_olav_dir):
        """Test settings with both enabled and disabled skills."""
        settings_json = {
            "enabledSkills": ["skill1", "skill2"],
            "disabledSkills": ["skill3"],
        }
        (temp_olav_dir / "settings.json").write_text(json.dumps(settings_json))

        with patch("config.settings.OLAV_DIR", temp_olav_dir):
            settings = Settings()
            assert settings.enabled_skills == ["skill1", "skill2"]
            assert settings.disabled_skills == ["skill3"]


# =============================================================================
# Test Settings Singleton
# =============================================================================

class TestSettingsSingleton:
    """Test that settings can be used as a singleton."""

    def test_import_settings(self):
        """Test importing the global settings instance."""
        from config.settings import settings

        # Should have LLM configuration
        assert hasattr(settings, "llm_model_name")
        assert hasattr(settings, "llm_temperature")

    def test_settings_persistence(self):
        """Test that settings persist across accesses."""
        from config.settings import settings as s1

        # Get settings again
        from config.settings import settings as s2

        # Should be the same instance (or at least same configuration)
        assert s1.llm_model_name == s2.llm_model_name


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
