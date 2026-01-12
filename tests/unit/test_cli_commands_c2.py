"""
Unit tests for CLI Commands (Phase C-2).

Tests for ConfigCommand, SkillCommand, KnowledgeCommand, ValidateCommand,
and CLICommandFactory.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from olav.cli.cli_commands_c2 import (
    CLICommandFactory,
    ConfigCommand,
    KnowledgeCommand,
    SkillCommand,
    ValidateCommand,
)


# =============================================================================
# Test ConfigCommand
# =============================================================================


class TestConfigCommandInit:
    """Tests for ConfigCommand initialization."""

    def test_init_with_settings(self):
        """Test initialization with Settings instance."""
        mock_settings = Mock()
        mock_settings.llm_model_name = "gpt-4o"
        mock_settings.llm_provider = "openai"
        mock_settings.llm_temperature = 0.7
        mock_settings.llm_max_tokens = 4096

        cmd = ConfigCommand(mock_settings)

        assert cmd.settings is mock_settings


class TestConfigCommandShow:
    """Tests for ConfigCommand.show method."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings with all required attributes."""
        settings = Mock()
        settings.llm_model_name = "gpt-4o"
        settings.llm_provider = "openai"
        settings.llm_temperature = 0.7
        settings.llm_max_tokens = 4096
        settings.routing.confidence_threshold = 0.6
        settings.routing.fallback_skill = "general"
        settings.hitl.require_approval_for_write = True
        settings.hitl.require_approval_for_skill_update = False
        settings.hitl.approval_timeout_seconds = 300
        settings.diagnosis.macro_max_confidence = 0.8
        settings.diagnosis.micro_target_confidence = 0.9
        settings.diagnosis.max_diagnosis_iterations = 3
        settings.logging_settings.level = "INFO"
        settings.logging_settings.audit_enabled = True
        settings.enabled_skills = ["skill1", "skill2"]
        settings.disabled_skills = ["skill3"]
        return settings

    def test_show_all_configuration(self, mock_settings):
        """Test showing all configuration sections."""
        cmd = ConfigCommand(mock_settings)
        result = cmd.show()

        assert "OLAV Configuration" in result
        assert "[LLM Configuration]" in result
        assert "Model:       gpt-4o" in result
        assert "Provider:    openai" in result
        assert "Temperature: 0.7" in result
        assert "[Skill Routing]" in result
        assert "[Human-in-the-Loop (HITL)]" in result
        assert "[Diagnosis Parameters]" in result
        assert "[Logging]" in result

    def test_show_llm_section_only(self, mock_settings):
        """Test showing only LLM configuration."""
        cmd = ConfigCommand(mock_settings)
        result = cmd.show("llm")

        assert "[LLM Configuration]" in result
        assert "Model:       gpt-4o" in result
        assert "[Skill Routing]" not in result

    def test_show_routing_section_only(self, mock_settings):
        """Test showing only routing configuration."""
        cmd = ConfigCommand(mock_settings)
        result = cmd.show("routing")

        assert "[Skill Routing]" in result
        assert "Confidence Threshold: 0.6" in result
        assert "[LLM Configuration]" not in result

    def test_show_hitl_section_only(self, mock_settings):
        """Test showing only HITL configuration."""
        cmd = ConfigCommand(mock_settings)
        result = cmd.show("hitl")

        assert "[Human-in-the-Loop (HITL)]" in result
        assert "Approve Write Ops:     True" in result
        assert "Approve Skill Updates: False" in result
        assert "Approval Timeout:      300s" in result

    def test_show_diagnosis_section_only(self, mock_settings):
        """Test showing only diagnosis configuration."""
        cmd = ConfigCommand(mock_settings)
        result = cmd.show("diagnosis")

        assert "[Diagnosis Parameters]" in result
        assert "Macro Max Confidence:   0.8" in result
        assert "Micro Target Confidence: 0.9" in result
        assert "Max Iterations:          3" in result

    def test_show_logging_section_only(self, mock_settings):
        """Test showing only logging configuration."""
        cmd = ConfigCommand(mock_settings)
        result = cmd.show("logging")

        assert "[Logging]" in result
        assert "Level:        INFO" in result
        assert "Audit Enabled: True" in result

    def test_show_skills_section_only(self, mock_settings):
        """Test showing only skills configuration."""
        cmd = ConfigCommand(mock_settings)
        result = cmd.show("skills")

        assert "[Skills Configuration]" in result
        assert "Enabled Skills:  skill1, skill2" in result
        assert "Disabled Skills: skill3" in result

    def test_show_empty_skills(self, mock_settings):
        """Test showing skills configuration with empty lists."""
        mock_settings.enabled_skills = []
        mock_settings.disabled_skills = []
        cmd = ConfigCommand(mock_settings)
        result = cmd.show("skills")

        assert "Enabled Skills:  (all)" in result
        assert "Disabled Skills: (none)" in result


class TestConfigCommandSet:
    """Tests for ConfigCommand.set method."""

    @pytest.fixture
    def config_command(self):
        """Create ConfigCommand with mock settings."""
        mock_settings = Mock()
        mock_settings.llm_model_name = "gpt-4o"
        mock_settings.llm_temperature = 0.7
        mock_settings.routing.confidence_threshold = 0.6
        mock_settings.hitl.require_approval_for_write = True
        mock_settings.diagnosis.macro_max_confidence = 0.8
        return ConfigCommand(mock_settings)

    def test_set_invalid_format(self, config_command):
        """Test set with invalid format (no equals sign)."""
        result = config_command.set("llm.model")

        assert "Error: Format should be 'key=value'" in result

    def test_set_llm_model(self, config_command):
        """Test setting LLM model."""
        with patch("config.settings.OLAV_DIR", Path("/mock/.olav")):
            with patch.object(config_command.settings, "save_to_json"):
                result = config_command.set("llm.model=gpt-4")

        assert "✓ Configuration updated: llm.model = gpt-4" in result
        assert config_command.settings.llm_model_name == "gpt-4"

    def test_set_llm_temperature(self, config_command):
        """Test setting LLM temperature."""
        with patch("config.settings.OLAV_DIR", Path("/mock/.olav")):
            with patch.object(config_command.settings, "save_to_json"):
                result = config_command.set("llm.temperature=0.5")

        assert "✓ Configuration updated" in result
        assert config_command.settings.llm_temperature == 0.5

    def test_set_routing_confidence_threshold(self, config_command):
        """Test setting routing confidence threshold."""
        with patch("config.settings.OLAV_DIR", Path("/mock/.olav")):
            with patch.object(config_command.settings, "save_to_json"):
                result = config_command.set("routing.confidence_threshold=0.8")

        assert "✓ Configuration updated" in result

    def test_set_hitl_approval_boolean_true(self, config_command):
        """Test setting HITL approval to true."""
        with patch("config.settings.OLAV_DIR", Path("/mock/.olav")):
            with patch.object(config_command.settings, "save_to_json"):
                result = config_command.set("hitl.require_approval_for_write=true")

        assert "✓ Configuration updated" in result
        assert config_command.settings.hitl.require_approval_for_write is True

    def test_set_hitl_approval_boolean_false(self, config_command):
        """Test setting HITL approval to false."""
        with patch("config.settings.OLAV_DIR", Path("/mock/.olav")):
            with patch.object(config_command.settings, "save_to_json"):
                result = config_command.set("hitl.require_approval_for_write=false")

        assert "✓ Configuration updated" in result

    def test_set_boolean_yes(self, config_command):
        """Test setting boolean with 'yes'."""
        with patch("config.settings.OLAV_DIR", Path("/mock/.olav")):
            with patch.object(config_command.settings, "save_to_json"):
                config_command.set("hitl.require_approval_for_write=yes")

        assert config_command.settings.hitl.require_approval_for_write is True

    def test_set_boolean_no(self, config_command):
        """Test setting boolean with 'no'."""
        with patch("config.settings.OLAV_DIR", Path("/mock/.olav")):
            with patch.object(config_command.settings, "save_to_json"):
                config_command.set("hitl.require_approval_for_write=no")

        assert config_command.settings.hitl.require_approval_for_write is False

    def test_set_boolean_1(self, config_command):
        """Test setting boolean with '1'."""
        with patch("config.settings.OLAV_DIR", Path("/mock/.olav")):
            with patch.object(config_command.settings, "save_to_json"):
                config_command.set("hitl.require_approval_for_write=1")

        assert config_command.settings.hitl.require_approval_for_write is True

    def test_set_boolean_0(self, config_command):
        """Test setting boolean with '0'."""
        with patch("config.settings.OLAV_DIR", Path("/mock/.olav")):
            with patch.object(config_command.settings, "save_to_json"):
                config_command.set("hitl.require_approval_for_write=0")

        assert config_command.settings.hitl.require_approval_for_write is False

    def test_set_diagnosis_macro_max_confidence(self, config_command):
        """Test setting diagnosis macro max confidence."""
        with patch("config.settings.OLAV_DIR", Path("/mock/.olav")):
            with patch.object(config_command.settings, "save_to_json"):
                result = config_command.set("diagnosis.macro_max_confidence=0.9")

        assert "✓ Configuration updated" in result

    def test_set_unknown_key(self, config_command):
        """Test setting unknown configuration key."""
        result = config_command.set("unknown.key=value")

        assert "Error: Unknown configuration key 'unknown.key'" in result

    def test_set_invalid_value_type(self, config_command):
        """Test setting with invalid value type."""
        with patch("config.settings.OLAV_DIR", Path("/mock/.olav")):
            with patch.object(
                config_command.settings, "llm_temperature", side_effect=ValueError
            ):
                result = config_command.set("llm.temperature=invalid")

        assert "Error: Invalid value" in result


class TestConfigCommandValidate:
    """Tests for ConfigCommand.validate method."""

    @pytest.fixture
    def valid_settings(self):
        """Create settings with valid values."""
        settings = Mock()
        settings.llm_model_name = "gpt-4o"
        settings.llm_temperature = 0.7
        settings.routing.confidence_threshold = 0.6
        settings.hitl.approval_timeout_seconds = 300
        return settings

    def test_validate_all_pass(self, valid_settings):
        """Test validation with all valid settings."""
        with patch("config.settings.OLAV_DIR") as mock_olav_dir:
            mock_settings_file = Mock()
            mock_settings_file.exists = Mock(return_value=True)
            mock_olav_dir.__truediv__ = Mock(return_value=mock_settings_file)

            cmd = ConfigCommand(valid_settings)
            result = cmd.validate()

        assert "Validating OLAV Configuration..." in result
        assert "✓ LLM model configured: gpt-4o" in result
        assert "✓ LLM temperature valid: 0.7" in result
        assert "✓ Routing threshold valid: 0.6" in result
        assert "✓ HITL timeout valid: 300s" in result
        assert "✓ All configuration checks passed" in result

    def test_validate_empty_model_name(self):
        """Test validation with empty model name."""
        settings = Mock()
        settings.llm_model_name = ""
        settings.llm_temperature = 0.7
        settings.routing.confidence_threshold = 0.6
        settings.hitl.approval_timeout_seconds = 300

        cmd = ConfigCommand(settings)
        result = cmd.validate()

        assert "❌ LLM model name is empty" in result

    def test_validate_temperature_out_of_bounds_high(self):
        """Test validation with temperature too high."""
        settings = Mock()
        settings.llm_model_name = "gpt-4o"
        settings.llm_temperature = 2.5
        settings.routing.confidence_threshold = 0.6
        settings.hitl.approval_timeout_seconds = 300

        cmd = ConfigCommand(settings)
        result = cmd.validate()

        assert "❌ LLM temperature out of bounds: 2.5" in result

    def test_validate_temperature_out_of_bounds_low(self):
        """Test validation with temperature too low."""
        settings = Mock()
        settings.llm_model_name = "gpt-4o"
        settings.llm_temperature = -0.1
        settings.routing.confidence_threshold = 0.6
        settings.hitl.approval_timeout_seconds = 300

        cmd = ConfigCommand(settings)
        result = cmd.validate()

        assert "❌ LLM temperature out of bounds: -0.1" in result

    def test_validate_confidence_threshold_out_of_bounds(self):
        """Test validation with confidence threshold out of bounds."""
        settings = Mock()
        settings.llm_model_name = "gpt-4o"
        settings.llm_temperature = 0.7
        settings.routing.confidence_threshold = 1.5
        settings.hitl.approval_timeout_seconds = 300

        cmd = ConfigCommand(settings)
        result = cmd.validate()

        assert "❌ Confidence threshold out of bounds: 1.5" in result

    def test_validate_hitl_timeout_out_of_bounds_low(self):
        """Test validation with HITL timeout too low."""
        settings = Mock()
        settings.llm_model_name = "gpt-4o"
        settings.llm_temperature = 0.7
        settings.routing.confidence_threshold = 0.6
        settings.hitl.approval_timeout_seconds = 5

        cmd = ConfigCommand(settings)
        result = cmd.validate()

        assert "❌ HITL timeout out of bounds: 5" in result

    def test_validate_hitl_timeout_out_of_bounds_high(self):
        """Test validation with HITL timeout too high."""
        settings = Mock()
        settings.llm_model_name = "gpt-4o"
        settings.llm_temperature = 0.7
        settings.routing.confidence_threshold = 0.6
        settings.hitl.approval_timeout_seconds = 5000

        cmd = ConfigCommand(settings)
        result = cmd.validate()

        assert "❌ HITL timeout out of bounds: 5000" in result

    def test_validate_settings_file_not_found(self):
        """Test validation when settings file doesn't exist."""
        settings = Mock()
        settings.llm_model_name = "gpt-4o"
        settings.llm_temperature = 0.7
        settings.routing.confidence_threshold = 0.6
        settings.hitl.approval_timeout_seconds = 300

        with patch("config.settings.OLAV_DIR") as mock_olav_dir:
            mock_settings_file = Mock()
            mock_settings_file.exists = Mock(return_value=False)
            mock_olav_dir.__truediv__ = Mock(return_value=mock_settings_file)

            cmd = ConfigCommand(settings)
            result = cmd.validate()

        assert "⚠ Settings file not found" in result


# =============================================================================
# Test SkillCommand
# =============================================================================


class TestSkillCommandInit:
    """Tests for SkillCommand initialization."""

    def test_init_with_olav_dir(self, tmp_path):
        """Test initialization with custom olav_dir."""
        cmd = SkillCommand(olav_dir=tmp_path)

        assert cmd.olav_dir == tmp_path
        assert cmd.skills_dir == tmp_path / "skills"

    def test_init_without_olav_dir(self):
        """Test initialization with default olav_dir."""
        with patch("config.settings.OLAV_DIR", Path("/mock/.olav")):
            cmd = SkillCommand()

            assert cmd.olav_dir == Path("/mock/.olav")
            assert cmd.skills_dir == Path("/mock/.olav/skills")


class TestSkillCommandListSkills:
    """Tests for SkillCommand.list_skills method."""

    def test_list_skills_no_directory(self, tmp_path):
        """Test listing skills when directory doesn't exist."""
        cmd = SkillCommand(olav_dir=tmp_path)
        result = cmd.list_skills()

        assert "Skills directory not found" in result

    def test_list_skills_empty(self, tmp_path):
        """Test listing skills when directory is empty."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        cmd = SkillCommand(olav_dir=tmp_path)
        result = cmd.list_skills()

        assert "No skills found" in result

    def test_list_skills_with_files(self, tmp_path):
        """Test listing skills with skill files."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        (skills_dir / "skill1.md").write_text("# Skill 1")
        (skills_dir / "skill2.md").write_text("# Skill 2")

        cmd = SkillCommand(olav_dir=tmp_path)
        result = cmd.list_skills()

        assert "Available Skills" in result
        assert "• skill1" in result
        assert "• skill2" in result
        assert "Total: 2 skill(s)" in result

    def test_list_skills_ignores_hidden(self, tmp_path):
        """Test that hidden skills (starting with _) are ignored."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        (skills_dir / "skill1.md").write_text("# Skill 1")
        (skills_dir / "_hidden.md").write_text("# Hidden")

        cmd = SkillCommand(olav_dir=tmp_path)
        result = cmd.list_skills()

        assert "• skill1" in result
        assert "• _hidden" not in result
        assert "Total: 1 skill(s)" in result

    def test_list_skills_sorted(self, tmp_path):
        """Test that skills are sorted alphabetically."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        (skills_dir / "zebra.md").write_text("# Zebra")
        (skills_dir / "apple.md").write_text("# Apple")

        cmd = SkillCommand(olav_dir=tmp_path)
        result = cmd.list_skills()

        lines = result.split("\n")
        apple_idx = next(i for i, line in enumerate(lines) if "• apple" in line)
        zebra_idx = next(i for i, line in enumerate(lines) if "• zebra" in line)

        assert apple_idx < zebra_idx

    def test_list_skills_with_category_filter(self, tmp_path):
        """Test listing skills with category filter."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        (skills_dir / "inspection-skill.md").write_text("# Inspection")
        (skills_dir / "general-skill.md").write_text("# General")

        cmd = SkillCommand(olav_dir=tmp_path)
        result = cmd.list_skills(category="inspection")

        assert "• inspection-skill" in result
        assert "• general-skill" not in result


class TestSkillCommandShowSkill:
    """Tests for SkillCommand.show_skill method."""

    def test_show_skill_not_found(self, tmp_path):
        """Test showing a skill that doesn't exist."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        cmd = SkillCommand(olav_dir=tmp_path)
        result = cmd.show_skill("nonexistent")

        assert "Skill not found: nonexistent" in result

    def test_show_skill_success(self, tmp_path):
        """Test showing a skill successfully."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_content = "# My Skill\n\nThis is a test skill.\n\n" + "\n".join([f"Line {i}" for i in range(100)])
        (skills_dir / "test-skill.md").write_text(skill_content)

        cmd = SkillCommand(olav_dir=tmp_path)
        result = cmd.show_skill("test-skill")

        assert "# My Skill" in result
        assert "This is a test skill" in result
        # Should be truncated to 50 lines (excluding header lines)
        assert "Line 45" in result
        assert "Line 47" not in result  # Lines 0-45 = 46 lines, plus 4 header lines = 50 total
        assert "for full content" in result

    def test_show_skill_read_error(self, tmp_path):
        """Test handling read error when showing skill."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_file = skills_dir / "test-skill.md"
        skill_file.write_text("# Test")

        cmd = SkillCommand(olav_dir=tmp_path)

        with patch.object(Path, "read_text", side_effect=PermissionError("Access denied")):
            result = cmd.show_skill("test-skill")

        assert "Error reading skill" in result


class TestSkillCommandSearchSkills:
    """Tests for SkillCommand.search_skills method."""

    def test_search_skills_no_directory(self, tmp_path):
        """Test searching when skills directory doesn't exist."""
        cmd = SkillCommand(olav_dir=tmp_path)
        result = cmd.search_skills("test")

        assert "Skills directory not found" in result

    def test_search_skills_no_results(self, tmp_path):
        """Test searching with no matching skills."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        (skills_dir / "skill1.md").write_text("# Skill 1")

        cmd = SkillCommand(olav_dir=tmp_path)
        result = cmd.search_skills("nonexistent")

        assert "Searching for skills matching 'nonexistent'" in result
        assert "No matching skills found" in result

    def test_search_skills_with_results(self, tmp_path):
        """Test searching with matching skills."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        (skills_dir / "inspection-skill.md").write_text("# Inspection")
        (skills_dir / "general-skill.md").write_text("# General")

        cmd = SkillCommand(olav_dir=tmp_path)
        result = cmd.search_skills("inspection")

        assert "Searching for skills matching 'inspection'" in result
        assert "✓ inspection-skill" in result
        assert "Found 1 skill(s)" in result

    def test_search_skills_case_insensitive(self, tmp_path):
        """Test that search is case-insensitive."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        (skills_dir / "Network-Skill.md").write_text("# Network")

        cmd = SkillCommand(olav_dir=tmp_path)
        result = cmd.search_skills("network")

        assert "✓ Network-Skill" in result

    def test_search_skills_ignores_hidden(self, tmp_path):
        """Test that search ignores hidden skills."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        (skills_dir / "test-skill.md").write_text("# Test")
        (skills_dir / "_hidden-test.md").write_text("# Hidden")

        cmd = SkillCommand(olav_dir=tmp_path)
        result = cmd.search_skills("test")

        assert "✓ test-skill" in result
        assert "_hidden-test" not in result


# =============================================================================
# Test KnowledgeCommand
# =============================================================================


class TestKnowledgeCommandInit:
    """Tests for KnowledgeCommand initialization."""

    def test_init_with_olav_dir(self, tmp_path):
        """Test initialization with custom olav_dir."""
        cmd = KnowledgeCommand(olav_dir=tmp_path)

        assert cmd.olav_dir == tmp_path
        assert cmd.knowledge_dir == tmp_path / "knowledge"

    def test_init_without_olav_dir(self):
        """Test initialization with default olav_dir."""
        with patch("config.settings.OLAV_DIR", Path("/mock/.olav")):
            cmd = KnowledgeCommand()

            assert cmd.olav_dir == Path("/mock/.olav")
            assert cmd.knowledge_dir == Path("/mock/.olav/knowledge")


class TestKnowledgeCommandListKnowledge:
    """Tests for KnowledgeCommand.list_knowledge method."""

    def test_list_knowledge_no_directory(self, tmp_path):
        """Test listing when knowledge directory doesn't exist."""
        cmd = KnowledgeCommand(olav_dir=tmp_path)
        result = cmd.list_knowledge()

        assert "Knowledge directory not found" in result

    def test_list_knowledge_empty(self, tmp_path):
        """Test listing when knowledge directory is empty."""
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()

        cmd = KnowledgeCommand(olav_dir=tmp_path)
        result = cmd.list_knowledge()

        assert "Knowledge Base" in result
        assert "Total: 0 item(s)" in result

    def test_list_knowledge_root_files(self, tmp_path):
        """Test listing root knowledge files."""
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()

        (knowledge_dir / "item1.md").write_text("# Item 1")
        (knowledge_dir / "item2.md").write_text("# Item 2")

        cmd = KnowledgeCommand(olav_dir=tmp_path)
        result = cmd.list_knowledge()

        assert "[Root Knowledge]" in result
        assert "• item1" in result
        assert "• item2" in result
        assert "Total: 2 item(s)" in result

    def test_list_knowledge_with_solutions(self, tmp_path):
        """Test listing with solutions subdirectory."""
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()

        solutions_dir = knowledge_dir / "solutions"
        solutions_dir.mkdir()

        (solutions_dir / "solution1.md").write_text("# Solution 1")
        (knowledge_dir / "root.md").write_text("# Root")

        cmd = KnowledgeCommand(olav_dir=tmp_path)
        result = cmd.list_knowledge()

        assert "[Root Knowledge]" in result
        assert "[Solutions]" in result
        assert "• root" in result
        assert "• solution1" in result
        assert "Total: 2 item(s)" in result

    def test_list_knowledge_sorted(self, tmp_path):
        """Test that knowledge items are sorted."""
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()

        (knowledge_dir / "zebra.md").write_text("# Zebra")
        (knowledge_dir / "apple.md").write_text("# Apple")

        cmd = KnowledgeCommand(olav_dir=tmp_path)
        result = cmd.list_knowledge()

        lines = result.split("\n")
        apple_idx = next(i for i, line in enumerate(lines) if "• apple" in line)
        zebra_idx = next(i for i, line in enumerate(lines) if "• zebra" in line)

        assert apple_idx < zebra_idx


class TestKnowledgeCommandSearchKnowledge:
    """Tests for KnowledgeCommand.search_knowledge method."""

    def test_search_knowledge_no_directory(self, tmp_path):
        """Test searching when knowledge directory doesn't exist."""
        cmd = KnowledgeCommand(olav_dir=tmp_path)
        result = cmd.search_knowledge("test")

        assert "Knowledge directory not found" in result

    def test_search_knowledge_no_results(self, tmp_path):
        """Test searching with no results."""
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()

        (knowledge_dir / "item1.md").write_text("# Item 1")

        cmd = KnowledgeCommand(olav_dir=tmp_path)
        result = cmd.search_knowledge("nonexistent")

        assert "Searching knowledge base for 'nonexistent'" in result
        assert "No matching knowledge items found" in result

    def test_search_knowledge_root_level(self, tmp_path):
        """Test searching root level knowledge."""
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()

        (knowledge_dir / "network-troubleshooting.md").write_text("# Network")
        (knowledge_dir / "other.md").write_text("# Other")

        cmd = KnowledgeCommand(olav_dir=tmp_path)
        result = cmd.search_knowledge("network")

        assert "✓ network-troubleshooting.md" in result
        assert "Found 1 item(s)" in result

    def test_search_knowledge_recursive(self, tmp_path):
        """Test searching knowledge recursively in subdirectories."""
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()

        solutions_dir = knowledge_dir / "solutions"
        solutions_dir.mkdir()

        (solutions_dir / "bgp-issue.md").write_text("# BGP")
        (knowledge_dir / "root.md").write_text("# Root")

        cmd = KnowledgeCommand(olav_dir=tmp_path)
        result = cmd.search_knowledge("bgp")

        assert "✓ solutions/bgp-issue.md" in result

    def test_search_knowledge_case_insensitive(self, tmp_path):
        """Test that search is case-insensitive."""
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()

        (knowledge_dir / "Network-Issue.md").write_text("# Network")

        cmd = KnowledgeCommand(olav_dir=tmp_path)
        result = cmd.search_knowledge("network")

        assert "✓ Network-Issue.md" in result

    def test_search_knowledge_ignores_hidden(self, tmp_path):
        """Test that search ignores hidden files."""
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()

        (knowledge_dir / "test.md").write_text("# Test")
        (knowledge_dir / "_hidden.md").write_text("# Hidden")

        cmd = KnowledgeCommand(olav_dir=tmp_path)
        result = cmd.search_knowledge("test")

        assert "✓ test.md" in result
        assert "_hidden.md" not in result


class TestKnowledgeCommandAddSolution:
    """Tests for KnowledgeCommand.add_solution method."""

    def test_add_solution_new(self, tmp_path):
        """Test adding a new solution."""
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()

        cmd = KnowledgeCommand(olav_dir=tmp_path)
        result = cmd.add_solution("bgp-route-flap")

        assert "✓ New solution created" in result
        assert "bgp-route-flap.md" in result

        solutions_dir = knowledge_dir / "solutions"
        solution_file = solutions_dir / "bgp-route-flap.md"
        assert solution_file.exists()

        content = solution_file.read_text()
        assert "id: bgp-route-flap" in content
        assert "category: network-troubleshooting" in content
        assert "# Bgp Route Flap" in content

    def test_add_solution_already_exists(self, tmp_path):
        """Test adding a solution that already exists."""
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()

        solutions_dir = knowledge_dir / "solutions"
        solutions_dir.mkdir()
        (solutions_dir / "existing.md").write_text("# Existing")

        cmd = KnowledgeCommand(olav_dir=tmp_path)
        result = cmd.add_solution("existing")

        assert "Solution already exists: existing" in result

    def test_add_solution_creates_solutions_dir(self, tmp_path):
        """Test that add_solution creates solutions directory if needed."""
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()

        cmd = KnowledgeCommand(olav_dir=tmp_path)
        cmd.add_solution("test-solution")

        solutions_dir = knowledge_dir / "solutions"
        assert solutions_dir.exists()
        assert (solutions_dir / "test-solution.md").exists()

    def test_add_solution_template_content(self, tmp_path):
        """Test that solution template contains all required sections."""
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()

        cmd = KnowledgeCommand(olav_dir=tmp_path)
        cmd.add_solution("test-problem")

        solution_file = knowledge_dir / "solutions" / "test-problem.md"
        content = solution_file.read_text()

        assert "## Problem Description" in content
        assert "## Root Cause" in content
        assert "## Solution" in content
        assert "## Verification" in content
        assert "## Prevention" in content
        assert "## References" in content

    def test_add_solution_write_error(self, tmp_path):
        """Test handling write error when adding solution."""
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()

        cmd = KnowledgeCommand(olav_dir=tmp_path)

        with patch.object(Path, "write_text", side_effect=PermissionError("Access denied")):
            result = cmd.add_solution("test")

        assert "Error creating solution" in result


# =============================================================================
# Test ValidateCommand
# =============================================================================


class TestValidateCommandInit:
    """Tests for ValidateCommand initialization."""

    def test_init_with_olav_dir(self, tmp_path):
        """Test initialization with custom olav_dir."""
        cmd = ValidateCommand(olav_dir=tmp_path)

        assert cmd.olav_dir == tmp_path

    def test_init_without_olav_dir(self):
        """Test initialization with default olav_dir."""
        with patch("config.settings.OLAV_DIR", Path("/mock/.olav")):
            cmd = ValidateCommand()

            assert cmd.olav_dir == Path("/mock/.olav")


class TestValidateCommandValidateAll:
    """Tests for ValidateCommand.validate_all method."""

    def test_validate_all_core_files_missing(self, tmp_path):
        """Test validation with missing core files."""
        cmd = ValidateCommand(olav_dir=tmp_path)
        result = cmd.validate_all()

        assert "OLAV File Integrity Validation" in result
        assert "❌ OLAV.md (missing)" in result
        assert "Missing core file: OLAV.md" in result

    def test_validate_all_core_files_present(self, tmp_path):
        """Test validation with core files present."""
        # OLAV.md is now in parent of olav_dir (project root)
        (tmp_path.parent / "OLAV.md").write_text("# OLAV")

        cmd = ValidateCommand(olav_dir=tmp_path)
        result = cmd.validate_all()

        assert "✓ OLAV.md" in result

    def test_validate_all_directories_present(self, tmp_path):
        """Test validation with directories present."""
        (tmp_path.parent / "OLAV.md").write_text("# OLAV")
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "skill1.md").write_text("# Skill 1")

        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()
        (knowledge_dir / "item1.md").write_text("# Item 1")

        cmd = ValidateCommand(olav_dir=tmp_path)
        result = cmd.validate_all()

        assert "✓ skills/ (1 files)" in result
        assert "✓ knowledge/ (1 files)" in result

    def test_validate_all_directories_missing(self, tmp_path):
        """Test validation with directories missing."""
        (tmp_path.parent / "OLAV.md").write_text("# OLAV")

        cmd = ValidateCommand(olav_dir=tmp_path)
        result = cmd.validate_all()

        assert "⚠ skills/ (not found)" in result
        assert "⚠ knowledge/ (not found)" in result

    def test_validate_all_settings_json_valid(self, tmp_path):
        """Test validation with valid settings.json."""
        (tmp_path.parent / "OLAV.md").write_text("# OLAV")

        settings_file = tmp_path / "settings.json"
        settings_file.write_text('{"llm_model_name": "gpt-4o"}')

        cmd = ValidateCommand(olav_dir=tmp_path)
        result = cmd.validate_all()

        assert "✓ settings.json (valid JSON)" in result

    def test_validate_all_settings_json_invalid(self, tmp_path):
        """Test validation with invalid settings.json."""
        (tmp_path.parent / "OLAV.md").write_text("# OLAV")

        settings_file = tmp_path / "settings.json"
        settings_file.write_text("{invalid json}")

        cmd = ValidateCommand(olav_dir=tmp_path)
        result = cmd.validate_all()

        assert "❌ settings.json (invalid JSON" in result
        assert "Invalid JSON in settings.json" in result

    def test_validate_all_settings_not_found(self, tmp_path):
        """Test validation when settings.json doesn't exist."""
        (tmp_path.parent / "OLAV.md").write_text("# OLAV")

        cmd = ValidateCommand(olav_dir=tmp_path)
        result = cmd.validate_all()

        assert "⚠ settings.json (not found, using defaults)" in result

    def test_validate_all_with_issues(self, tmp_path):
        """Test validation reports issues correctly."""
        cmd = ValidateCommand(olav_dir=tmp_path)
        result = cmd.validate_all()

        # Test detects missing directories and missing settings.json
        assert "⚠ skills/ (not found)" in result
        assert "⚠ knowledge/ (not found)" in result
        assert "⚠ settings.json (not found, using defaults)" in result

    def test_validate_all_success(self, tmp_path):
        """Test validation passes all checks."""
        # OLAV.md is now in parent of olav_dir (project root)
        (tmp_path.parent / "OLAV.md").write_text("# OLAV")
        (tmp_path / "skills").mkdir()
        (tmp_path / "knowledge").mkdir()
        (tmp_path / "settings.json").write_text('{}')

        cmd = ValidateCommand(olav_dir=tmp_path)
        result = cmd.validate_all()

        assert "✓ All validation checks passed" in result


# =============================================================================
# Test CLICommandFactory
# =============================================================================


class TestCLICommandFactoryInit:
    """Tests for CLICommandFactory initialization."""

    def test_init_with_settings_and_olav_dir(self, tmp_path):
        """Test initialization with settings and olav_dir."""
        mock_settings = Mock()
        cmd_factory = CLICommandFactory(mock_settings, olav_dir=tmp_path)

        assert cmd_factory.settings is mock_settings
        assert cmd_factory.olav_dir == tmp_path

    def test_init_with_default_olav_dir(self):
        """Test initialization with default olav_dir."""
        mock_settings = Mock()

        with patch("config.settings.OLAV_DIR", Path("/mock/.olav")):
            cmd_factory = CLICommandFactory(mock_settings)

            assert cmd_factory.olav_dir == Path("/mock/.olav")


class TestCLICommandFactoryCreateCommands:
    """Tests for CLICommandFactory create methods."""

    @pytest.fixture
    def command_factory(self, tmp_path):
        """Create a CLICommandFactory for testing."""
        mock_settings = Mock()
        return CLICommandFactory(mock_settings, olav_dir=tmp_path)

    def test_create_config_command(self, command_factory):
        """Test creating ConfigCommand."""
        cmd = command_factory.create_config_command()

        assert isinstance(cmd, ConfigCommand)
        assert cmd.settings is command_factory.settings

    def test_create_skill_command(self, command_factory):
        """Test creating SkillCommand."""
        cmd = command_factory.create_skill_command()

        assert isinstance(cmd, SkillCommand)
        assert cmd.olav_dir == command_factory.olav_dir

    def test_create_knowledge_command(self, command_factory):
        """Test creating KnowledgeCommand."""
        cmd = command_factory.create_knowledge_command()

        assert isinstance(cmd, KnowledgeCommand)
        assert cmd.olav_dir == command_factory.olav_dir

    def test_create_validate_command(self, command_factory):
        """Test creating ValidateCommand."""
        cmd = command_factory.create_validate_command()

        assert isinstance(cmd, ValidateCommand)
        assert cmd.olav_dir == command_factory.olav_dir
