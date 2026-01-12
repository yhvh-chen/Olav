"""
Unit tests for agent module.

Tests for OLAV DeepAgent creation and configuration.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from olav.agent import (
    _format_skills_for_prompt,
    create_olav_agent,
    create_subagent,
    get_inspector_agent,
    get_macro_analyzer,
    get_micro_analyzer,
    initialize_olav,
)


# =============================================================================
# Test _format_skills_for_prompt
# =============================================================================


class TestFormatSkillsForPrompt:
    """Tests for _format_skills_for_prompt function."""

    def test_format_skills_empty(self):
        """Test formatting with no skills."""
        result = _format_skills_for_prompt({})

        assert "When approaching tasks" in result

    def test_format_skills_single_skill(self):
        """Test formatting with one skill."""
        skills = {
            "test_skill": Mock(
                complexity="low",
                description="Test description"
            )
        }

        result = _format_skills_for_prompt(skills)

        assert "test_skill" in result
        assert "(low)" in result
        assert "Test description" in result

    def test_format_skills_multiple_skills(self):
        """Test formatting with multiple skills."""
        skills = {
            "skill1": Mock(complexity="low", description="Description 1"),
            "skill2": Mock(complexity="high", description="Description 2"),
        }

        result = _format_skills_for_prompt(skills)

        assert "skill1" in result
        assert "skill2" in result
        assert "Description 1" in result
        assert "Description 2" in result


# =============================================================================
# Test create_subagent
# =============================================================================


class TestCreateSubagent:
    """Tests for create_subagent function."""

    def test_create_subagent_basic(self):
        """Test creating basic subagent config."""
        result = create_subagent(
            name="test",
            description="Test subagent",
            system_prompt="Test prompt",
        )

        assert result["name"] == "test"
        assert result["description"] == "Test subagent"
        assert result["system_prompt"] == "Test prompt"
        assert result["tools"] == []

    def test_create_subagent_with_tools(self):
        """Test creating subagent with tools."""
        mock_tool = Mock()
        result = create_subagent(
            name="test",
            description="Test",
            system_prompt="Prompt",
            tools=[mock_tool],
        )

        assert result["tools"] == [mock_tool]


# =============================================================================
# Test get_macro_analyzer
# =============================================================================


class TestGetMacroAnalyzer:
    """Tests for get_macro_analyzer function."""

    def test_get_macro_analyzer_structure(self):
        """Test macro-analyzer subagent structure."""
        result = get_macro_analyzer()

        assert result["name"] == "macro-analyzer"
        assert "macro analysis" in result["description"].lower()
        assert result["system_prompt"] is not None
        assert len(result["tools"]) == 3


# =============================================================================
# Test get_micro_analyzer
# =============================================================================


class TestGetMicroAnalyzer:
    """Tests for get_micro_analyzer function."""

    def test_get_micro_analyzer_structure(self):
        """Test micro-analyzer subagent structure."""
        result = get_micro_analyzer()

        assert result["name"] == "micro-analyzer"
        assert "micro analysis" in result["description"].lower()
        assert result["system_prompt"] is not None
        assert len(result["tools"]) == 2


# =============================================================================
# Test get_inspector_agent
# =============================================================================


class TestGetInspectorAgent:
    """Tests for get_inspector_agent function."""

    def test_get_inspector_agent_structure(self):
        """Test inspector-agent subagent structure."""
        result = get_inspector_agent()

        assert result["name"] == "inspector-agent"
        assert "inspection" in result["description"].lower()
        assert result["system_prompt"] is not None
        assert len(result["tools"]) == 3


# =============================================================================
# Test create_olav_agent
# =============================================================================


class TestCreateOlavAgent:
    """Tests for create_olav_agent function."""

    def test_create_agent_enable_hitl_default(self):
        """Test agent with HITL enabled by default."""
        mock_agent = Mock()
        mock_llm = Mock()

        with patch("olav.agent.LLMFactory.get_chat_model", return_value=mock_llm):
            with patch("olav.agent.create_deep_agent", return_value=mock_agent) as mock_create:
                with patch("olav.agent.get_skill_loader") as mock_loader:
                    with patch("olav.agent.get_storage_permissions", return_value=""):
                        with patch("olav.agent.settings") as mock_settings:
                            mock_settings.enable_hitl = True
                            mock_settings.agent_dir = "/test"

                            mock_loader_instance = Mock()
                            mock_loader_instance.load_all.return_value = {}
                            mock_loader.return_value = mock_loader_instance

                            result = create_olav_agent()

                            # Verify agent was created
                            mock_create.assert_called_once()
                            # Verify HITL was enabled
                            call_kwargs = mock_create.call_args.kwargs
                            assert "interrupt_on" in call_kwargs

    def test_create_agent_disable_hitl(self):
        """Test agent with HITL disabled."""
        mock_agent = Mock()
        mock_llm = Mock()

        with patch("olav.agent.LLMFactory.get_chat_model", return_value=mock_llm):
            with patch("olav.agent.create_deep_agent", return_value=mock_agent) as mock_create:
                with patch("olav.agent.get_skill_loader") as mock_loader:
                    with patch("olav.agent.get_storage_permissions", return_value=""):
                        with patch("olav.agent.settings") as mock_settings:
                            mock_settings.enable_hitl = True

                            mock_loader_instance = Mock()
                            mock_loader_instance.load_all.return_value = {}
                            mock_loader.return_value = mock_loader_instance

                            result = create_olav_agent(enable_hitl=False)

                            # Verify HITL was disabled
                            call_kwargs = mock_create.call_args.kwargs
                            assert call_kwargs["interrupt_on"] is None

    def test_create_agent_custom_model(self):
        """Test agent with custom model."""
        mock_agent = Mock()
        mock_llm = Mock()

        with patch("olav.agent.LLMFactory.get_chat_model", return_value=mock_llm):
            with patch("olav.agent.create_deep_agent", return_value=mock_agent) as mock_create:
                with patch("olav.agent.get_skill_loader") as mock_loader:
                    with patch("olav.agent.get_storage_permissions", return_value=""):
                        with patch("olav.agent.settings") as mock_settings:
                            mock_settings.enable_hitl = True
                            mock_settings.agent_dir = "/test"

                            mock_loader_instance = Mock()
                            mock_loader_instance.load_all.return_value = {}
                            mock_loader.return_value = mock_loader_instance

                            result = create_olav_agent(model="gpt-4")

                            # Verify custom model was used
                            call_kwargs = mock_create.call_args.kwargs
                            assert call_kwargs["model"] == mock_llm

    def test_create_agent_with_skills(self):
        """Test agent with skill routing enabled."""
        mock_agent = Mock()
        mock_llm = Mock()

        with patch("olav.agent.LLMFactory.get_chat_model", return_value=mock_llm):
            with patch("olav.agent.create_deep_agent", return_value=mock_agent) as mock_create:
                with patch("olav.agent.get_skill_loader") as mock_loader:
                    with patch("olav.agent.get_storage_permissions", return_value=""):
                        with patch("olav.agent.settings") as mock_settings:
                            mock_settings.enable_hitl = True
                            mock_settings.agent_dir = "/test"

                            mock_skill = Mock(complexity="low", description="Test skill")
                            mock_loader_instance = Mock()
                            mock_loader_instance.load_all.return_value = {"skill1": mock_skill}
                            mock_loader.return_value = mock_loader_instance

                            result = create_olav_agent(enable_skill_routing=True)

                            # Verify skills were included in system prompt
                            call_kwargs = mock_create.call_args.kwargs
                            system_prompt = call_kwargs["system_prompt"]
                            assert "skill1" in system_prompt

    def test_create_agent_without_skills(self):
        """Test agent with skill routing disabled."""
        mock_agent = Mock()
        mock_llm = Mock()

        with patch("olav.agent.LLMFactory.get_chat_model", return_value=mock_llm):
            with patch("olav.agent.create_deep_agent", return_value=mock_agent) as mock_create:
                with patch("olav.agent.get_skill_loader") as mock_loader:
                    with patch("olav.agent.get_storage_permissions", return_value=""):
                        with patch("olav.agent.settings") as mock_settings:
                            mock_settings.enable_hitl = True
                            mock_settings.agent_dir = "/test"

                            mock_loader_instance = Mock()
                            mock_loader_instance.load_all.return_value = {}
                            mock_loader.return_value = mock_loader_instance

                            result = create_olav_agent(enable_skill_routing=False)

                            # Skills should not be mentioned
                            call_kwargs = mock_create.call_args.kwargs
                            system_prompt = call_kwargs["system_prompt"]

    def test_create_agent_olav_md_exists(self, tmp_path):
        """Test agent loads OLAV.md if exists."""
        mock_agent = Mock()
        mock_llm = Mock()

        custom_prompt = "Custom OLAV prompt"

        with patch("olav.agent.LLMFactory.get_chat_model", return_value=mock_llm):
            with patch("olav.agent.create_deep_agent", return_value=mock_agent) as mock_create:
                with patch("olav.agent.get_skill_loader") as mock_loader:
                    with patch("olav.agent.get_storage_permissions", return_value=""):
                        with patch("olav.agent.settings") as mock_settings:
                            mock_settings.enable_hitl = True
                            mock_settings.agent_dir = str(tmp_path)

                            mock_loader_instance = Mock()
                            mock_loader_instance.load_all.return_value = {}
                            mock_loader.return_value = mock_loader_instance

                            # Mock Path("OLAV.md").exists() to return True and read_text to return custom prompt
                            with patch("olav.agent.Path") as mock_path_class:
                                mock_path_instance = Mock()
                                mock_path_instance.exists.return_value = True
                                mock_path_instance.read_text.return_value = custom_prompt
                                mock_path_class.return_value = mock_path_instance

                                result = create_olav_agent()

                                # Verify custom prompt was used
                                call_kwargs = mock_create.call_args.kwargs
                                assert custom_prompt in call_kwargs["system_prompt"]


# =============================================================================
# Test initialize_olav
# =============================================================================


class TestInitializeOlav:
    """Tests for initialize_olav function."""

    def test_initialize_olav(self):
        """Test OLAV initialization."""
        mock_agent = Mock()
        mock_counts = {"commands": 10, "apis": 5, "total": 15}

        with patch("olav.agent.create_olav_agent", return_value=mock_agent):
            with patch("olav.agent.reload_capabilities", return_value=mock_counts):
                with patch("olav.agent.settings") as mock_settings:
                    with patch("builtins.print"):
                        mock_settings.agent_dir = "/test/olav"

                        result = initialize_olav()

                        assert result == mock_agent

    def test_initialize_olav_reloads_capabilities(self):
        """Test that initialize_olav reloads capabilities."""
        mock_agent = Mock()
        mock_counts = {"commands": 10, "apis": 5, "total": 15}

        with patch("olav.agent.create_olav_agent", return_value=mock_agent):
            with patch("olav.agent.reload_capabilities", return_value=mock_counts) as mock_reload:
                with patch("olav.agent.settings") as mock_settings:
                    with patch("builtins.print"):
                        mock_settings.agent_dir = "/test/olav"

                        result = initialize_olav()

                        # Verify reload was called
                        mock_reload.assert_called_once()
