"""Unit tests for unified configuration module.

Tests the simplified config architecture where all settings are in config/settings.py
and loaded from .env file.
"""

import pytest

from config.settings import (
    EnvSettings,
    settings,
    PROJECT_ROOT,
    DATA_DIR,
    CONFIG_DIR,
    get_path,
)


class TestEnvSettings:
    """Tests for environment settings loaded from .env."""

    def test_settings_singleton(self):
        """Test settings is a singleton instance."""
        assert isinstance(settings, EnvSettings)

    def test_postgres_uri_auto_built(self):
        """Test PostgreSQL URI is auto-built."""
        assert settings.postgres_uri != ""
        assert "postgresql://" in settings.postgres_uri

    def test_opensearch_url_auto_built(self):
        """Test OpenSearch URL is auto-built."""
        assert settings.opensearch_url != ""
        assert "http" in settings.opensearch_url

    def test_redis_url_auto_built(self):
        """Test Redis URL is optional (only set when configured)."""
        assert settings.redis_url == "" or "redis://" in settings.redis_url

    def test_llm_settings(self):
        """Test LLM settings have defaults."""
        assert settings.llm_provider in ("openai", "ollama", "azure")
        assert settings.llm_model_name != ""
        assert settings.llm_temperature >= 0 and settings.llm_temperature <= 1
        assert settings.llm_max_tokens > 0

    def test_feature_flags_are_booleans(self):
        """Test feature flags are boolean values."""
        assert isinstance(settings.use_dynamic_router, bool)
        assert isinstance(settings.enable_agentic_rag, bool)
        assert isinstance(settings.stream_stateless, bool)
        assert isinstance(settings.enable_guard_mode, bool)
        assert isinstance(settings.enable_hitl, bool)

    def test_agent_settings(self):
        """Test agent settings have valid defaults."""
        assert 1 <= settings.agent_max_tool_calls <= 50
        assert settings.agent_memory_window > 0
        assert settings.agent_language in ("auto", "zh", "en")

    def test_diagnosis_settings(self):
        """Test diagnosis settings have valid defaults."""
        assert settings.diagnosis_max_iterations > 0
        assert 0 < settings.diagnosis_confidence_threshold <= 1
        assert settings.diagnosis_methodology in ("funnel", "parallel")


class TestProjectPaths:
    """Tests for project path constants."""

    def test_project_root_exists(self):
        """Test PROJECT_ROOT is valid."""
        assert PROJECT_ROOT.exists()

    def test_data_dir_is_under_project(self):
        """Test DATA_DIR is under PROJECT_ROOT."""
        assert str(DATA_DIR).startswith(str(PROJECT_ROOT))

    def test_config_dir_is_under_project(self):
        """Test CONFIG_DIR is under PROJECT_ROOT."""
        assert str(CONFIG_DIR).startswith(str(PROJECT_ROOT))


class TestGetPath:
    """Tests for get_path helper function."""

    def test_get_suzieq_data_path(self):
        """Test get_path returns valid path for suzieq_data."""
        path = get_path("suzieq_data")
        assert path.is_absolute()
        assert "suzieq" in str(path)

    def test_get_documents_path(self):
        """Test get_path returns valid path for documents."""
        path = get_path("documents")
        assert path.is_absolute()
        assert "documents" in str(path)

    def test_get_prompts_path(self):
        """Test get_path returns valid path for prompts."""
        path = get_path("prompts")
        assert path.is_absolute()
        assert "prompts" in str(path)

    def test_get_inspections_path(self):
        """Test get_path returns valid path for inspections."""
        path = get_path("inspections")
        assert path.is_absolute()
        assert "inspections" in str(path)

    def test_get_path_unknown_raises(self):
        """Test get_path raises for unknown path names."""
        with pytest.raises(ValueError, match="Unknown path"):
            get_path("unknown_path_name")
