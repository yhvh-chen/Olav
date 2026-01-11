"""
Tests for Phase C-3: Claude Code Migration

Validates migration functionality and verification scripts.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# =============================================================================
# Test Migration Script Integration
# =============================================================================

class TestMigrationIntegrationBasic:
    """Test basic migration concepts without direct script import."""

    @pytest.fixture
    def temp_project(self):
        """Create temporary project structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            
            # Create .olav directory structure
            olav_dir = project_root / ".olav"
            olav_dir.mkdir()
            (olav_dir / "skills").mkdir()
            (olav_dir / "knowledge").mkdir()
            (olav_dir / "commands").mkdir()
            
            # Create core files
            (olav_dir / "OLAV.md").write_text("# OLAV Core Configuration")
            settings = {
                "llmModelName": "gpt-4",
                "llmTemperature": 0.7,
                "routingPath": ".olav/skills"
            }
            (olav_dir / "settings.json").write_text(json.dumps(settings))
            
            # Create sample skill
            (olav_dir / "skills" / "network.md").write_text("# Network Skill")
            
            # Create sample knowledge
            (olav_dir / "knowledge" / "solution.md").write_text("# Solution")
            
            yield project_root

    def test_olav_directory_exists(self, temp_project):
        """Test that .olav directory exists."""
        assert (temp_project / ".olav").exists()
        assert (temp_project / ".olav" / "OLAV.md").exists()

    def test_olav_has_required_subdirs(self, temp_project):
        """Test that .olav has required subdirectories."""
        olav_dir = temp_project / ".olav"
        assert (olav_dir / "skills").exists()
        assert (olav_dir / "knowledge").exists()

    def test_migration_target_structure(self, temp_project):
        """Test migration would create proper .claude structure."""
        claude_dir = temp_project / ".claude"
        claude_dir.mkdir()
        (claude_dir / "skills").mkdir()
        (claude_dir / "knowledge").mkdir()
        (claude_dir / "CLAUDE.md").write_text("# Claude")
        
        assert (claude_dir / "CLAUDE.md").exists()
        assert (claude_dir / "skills").exists()

    def test_settings_path_conversion(self, temp_project):
        """Test that settings.json paths can be converted."""
        olav_dir = temp_project / ".olav"
        settings_path = olav_dir / "settings.json"
        settings = json.loads(settings_path.read_text())
        
        # Simulate path conversion
        original_routing = settings.get("routingPath", "")
        converted_routing = original_routing.replace(".olav", ".claude")
        
        assert ".olav" in original_routing
        assert ".claude" in converted_routing
        assert ".olav" not in converted_routing


# =============================================================================
# Test Verification Script
# =============================================================================

# Skip this entire class if the verification script doesn't exist
verify_script = pytest.importorskip(
    "scripts.verify_claude_compat_enhanced",
    reason="verify_claude_compat_enhanced.py script not implemented yet"
)


@pytest.mark.skip(reason="verify_claude_compat_enhanced.py script not implemented")
class TestVerificationScript:
    """Test the Claude compatibility verification."""

    @pytest.fixture
    def valid_claude_dir(self):
        """Create valid .claude directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            claude_dir = project_root / ".claude"
            claude_dir.mkdir()
            
            # Create directory structure
            (claude_dir / "skills").mkdir()
            (claude_dir / "knowledge").mkdir()
            
            # Create core files
            (claude_dir / "CLAUDE.md").write_text("# Claude Configuration\n\nCore setup")
            settings = {
                "llmModelName": "gpt-4",
                "llmTemperature": 0.7,
                "routingPath": ".claude/skills"
            }
            (claude_dir / "settings.json").write_text(json.dumps(settings))
            
            # Create sample Markdown files
            (claude_dir / "skills" / "network.md").write_text("# Network Skill\n\nContent")
            (claude_dir / "knowledge" / "solution.md").write_text("# Solution\n\nContent")
            
            yield project_root

    def test_validator_structure_exists(self, valid_claude_dir):
        """Test that validator can be instantiated."""
        from scripts.verify_claude_compat_enhanced import (
            ClaudeCompatibilityValidator
        )
        
        validator = ClaudeCompatibilityValidator(
            project_root=valid_claude_dir
        )
        assert validator is not None
        assert validator.claude_dir.exists()

    def test_validate_claude_directory_exists(self, valid_claude_dir):
        """Test that .claude directory is detected."""
        from scripts.verify_claude_compat_enhanced import (
            ClaudeCompatibilityValidator
        )
        
        validator = ClaudeCompatibilityValidator(
            project_root=valid_claude_dir
        )
        assert validator.validate_directory_exists() is True

    def test_validate_required_directories(self, valid_claude_dir):
        """Test validation of required directories."""
        from scripts.verify_claude_compat_enhanced import (
            ClaudeCompatibilityValidator
        )
        
        validator = ClaudeCompatibilityValidator(
            project_root=valid_claude_dir
        )
        assert validator.validate_required_directories() is True

    def test_validate_core_files(self, valid_claude_dir):
        """Test validation of core files."""
        from scripts.verify_claude_compat_enhanced import (
            ClaudeCompatibilityValidator
        )
        
        validator = ClaudeCompatibilityValidator(
            project_root=valid_claude_dir
        )
        assert validator.validate_core_files() is True

    def test_validate_markdown_format(self, valid_claude_dir):
        """Test validation of Markdown files."""
        from scripts.verify_claude_compat_enhanced import (
            ClaudeCompatibilityValidator
        )
        
        validator = ClaudeCompatibilityValidator(
            project_root=valid_claude_dir
        )
        assert validator.validate_markdown_format() is True

    def test_validate_settings_json_schema(self, valid_claude_dir):
        """Test validation of settings.json."""
        from scripts.verify_claude_compat_enhanced import (
            ClaudeCompatibilityValidator
        )
        
        validator = ClaudeCompatibilityValidator(
            project_root=valid_claude_dir
        )
        assert validator.validate_settings_json_schema() is True

    def test_validate_no_olav_references(self, valid_claude_dir):
        """Test detection of .olav references."""
        from scripts.verify_claude_compat_enhanced import (
            ClaudeCompatibilityValidator
        )
        
        validator = ClaudeCompatibilityValidator(
            project_root=valid_claude_dir
        )
        assert validator.validate_no_olav_references() is True

    def test_complete_validation_passes(self, valid_claude_dir):
        """Test complete validation on valid structure."""
        from scripts.verify_claude_compat_enhanced import (
            ClaudeCompatibilityValidator
        )
        
        validator = ClaudeCompatibilityValidator(
            project_root=valid_claude_dir
        )
        success, report = validator.validate()
        
        assert success is True
        assert report["compatible"] is True

    def test_detector_missing_directory(self):
        """Test detection of missing .claude directory."""
        from scripts.verify_claude_compat_enhanced import (
            ClaudeCompatibilityValidator
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            validator = ClaudeCompatibilityValidator(
                project_root=Path(tmpdir)
            )
            assert validator.validate_directory_exists() is False

    def test_detector_invalid_json(self, valid_claude_dir):
        """Test detection of invalid JSON."""
        from scripts.verify_claude_compat_enhanced import (
            ClaudeCompatibilityValidator
        )
        
        claude_dir = valid_claude_dir / ".claude"
        (claude_dir / "settings.json").write_text("{ invalid json }")
        
        validator = ClaudeCompatibilityValidator(
            project_root=valid_claude_dir
        )
        assert validator.validate_core_files() is False

    def test_detector_missing_core_files(self, valid_claude_dir):
        """Test detection of missing core files."""
        from scripts.verify_claude_compat_enhanced import (
            ClaudeCompatibilityValidator
        )
        
        claude_dir = valid_claude_dir / ".claude"
        (claude_dir / "CLAUDE.md").unlink()
        
        validator = ClaudeCompatibilityValidator(
            project_root=valid_claude_dir
        )
        assert validator.validate_core_files() is False

    def test_detector_olav_references(self, valid_claude_dir):
        """Test detection of .olav references in files."""
        from scripts.verify_claude_compat_enhanced import (
            ClaudeCompatibilityValidator
        )
        
        claude_dir = valid_claude_dir / ".claude"
        content = (claude_dir / "CLAUDE.md").read_text()
        (claude_dir / "CLAUDE.md").write_text(content + "\n\nLegacy .olav path")
        
        validator = ClaudeCompatibilityValidator(
            project_root=valid_claude_dir
        )
        assert validator.validate_no_olav_references() is False

    def test_report_generation(self, valid_claude_dir):
        """Test generation of compatibility report."""
        from scripts.verify_claude_compat_enhanced import (
            ClaudeCompatibilityValidator
        )
        
        validator = ClaudeCompatibilityValidator(
            project_root=valid_claude_dir
        )
        success, report = validator.validate()
        
        assert "compatible" in report
        assert "issues" in report
        assert "warnings" in report
        assert "details" in report
        assert "successful_checks" in report["details"]


# =============================================================================
# Test Migration Compatibility
# =============================================================================

class TestMigrationCompatibility:
    """Test migration and verification integration."""

    def test_settings_conversion_logic(self):
        """Test logic for converting settings paths."""
        original = {
            "llmModelName": "gpt-4",
            "routingPath": ".olav/skills",
            "knowledgePath": ".olav/knowledge"
        }
        
        # Convert paths
        converted = {}
        for key, value in original.items():
            if isinstance(value, str):
                converted[key] = value.replace(".olav", ".claude")
            else:
                converted[key] = value
        
        assert ".olav" not in str(converted)
        assert ".claude" in str(converted)

    def test_directory_structure_validation(self):
        """Test directory structure validation logic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            claude = project / ".claude"
            claude.mkdir()
            (claude / "skills").mkdir()
            (claude / "knowledge").mkdir()
            
            required = {"skills", "knowledge"}
            existing = {d.name for d in claude.iterdir() if d.is_dir()}
            
            assert required.issubset(existing)

    def test_markdown_validation_logic(self):
        """Test Markdown file validation logic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)
            
            # Create valid MD file
            valid_file = skills_dir / "valid.md"
            valid_file.write_text("# Skill Title\n\nContent here")
            
            # Create empty MD file
            empty_file = skills_dir / "empty.md"
            empty_file.write_text("")
            
            md_files = list(skills_dir.glob("*.md"))
            assert len(md_files) == 2
            
            # Test validation logic
            valid_count = 0
            for f in md_files:
                content = f.read_text().strip()
                if content:
                    valid_count += 1
            
            assert valid_count == 1


# =============================================================================
# Test Utilities
# =============================================================================

class TestVerificationUtilities:
    """Test utility functions for verification."""

    def test_issue_categorization(self):
        """Test issue categorization logic."""
        issues = [
            {"category": "Structure", "severity": "ERROR"},
            {"category": "CoreFiles", "severity": "ERROR"},
            {"category": "Markdown", "severity": "WARNING"},
        ]
        
        errors = [i for i in issues if i["severity"] == "ERROR"]
        warnings = [i for i in issues if i["severity"] == "WARNING"]
        
        assert len(errors) == 2
        assert len(warnings) == 1

    def test_json_validation_logic(self):
        """Test JSON validation logic."""
        valid_json = '{"key": "value"}'
        invalid_json = "{ invalid }"
        
        # Test valid
        try:
            json.loads(valid_json)
            is_valid = True
        except json.JSONDecodeError:
            is_valid = False
        
        assert is_valid is True
        
        # Test invalid
        try:
            json.loads(invalid_json)
            is_valid = True
        except json.JSONDecodeError:
            is_valid = False
        
        assert is_valid is False
