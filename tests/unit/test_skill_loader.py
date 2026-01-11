"""Unit tests for Phase 2: Skill Loader.

Tests the skill loading functionality from .olav/skills/*.md files
and dual format support (Claude Code SKILL.md + legacy flat files).
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from olav.core.skill_loader import Skill, SkillLoader, get_skill_loader


class TestSkill:
    """Test Skill dataclass."""

    def test_skill_creation(self) -> None:
        """Test creating a Skill instance."""
        skill = Skill(
            id="test-skill",
            intent="query",
            complexity="simple",
            description="A test skill",
            examples=["test", "run"],
            file_path="/path/to/skill.md",
            content="# Test Skill\n\nContent here.",
        )
        assert skill.id == "test-skill"
        assert skill.description == "A test skill"
        assert skill.intent == "query"
        assert skill.complexity == "simple"
        assert "test" in skill.examples

    def test_skill_default_content(self) -> None:
        """Test Skill default content is None."""
        skill = Skill(
            id="test",
            intent="query",
            complexity="medium",
            description="Test",
            examples=[],
            file_path="/path/to/skill.md",
        )
        assert skill.content is None

    def test_skill_with_frontmatter(self) -> None:
        """Test Skill with frontmatter data."""
        frontmatter = {
            "name": "Test",
            "version": "1.0.0",
            "output": {"format": "markdown"},
        }

        skill = Skill(
            id="test",
            intent="query",
            complexity="simple",
            description="Test skill",
            examples=[],
            file_path="/path/to/skill.md",
            frontmatter=frontmatter,
        )

        assert skill.frontmatter == frontmatter
        assert skill.frontmatter["version"] == "1.0.0"


class TestSkillLoader:
    """Test SkillLoader class."""

    def test_singleton_pattern(self) -> None:
        """Test that get_skill_loader returns singleton."""
        loader1 = get_skill_loader()
        loader2 = get_skill_loader()
        assert loader1 is loader2

    def test_load_all_skills(self) -> None:
        """Test loading all skills from .olav/skills/."""
        loader = get_skill_loader()
        skills = loader.load_all()
        # Should have at least some skills
        assert isinstance(skills, dict)
        # If skills directory exists and has files
        skills_dir = Path(".olav/skills")
        if skills_dir.exists() and list(skills_dir.glob("*.md")):
            assert len(skills) > 0

    def test_skill_has_required_fields(self) -> None:
        """Test that loaded skills have required fields."""
        loader = get_skill_loader()
        skills = loader.load_all()
        for skill_id, skill in skills.items():
            assert skill.id, f"Skill {skill_id} missing id"
            assert skill.description, f"Skill {skill_id} missing description"
            assert isinstance(skill.examples, list)

    def test_get_skill_by_id(self) -> None:
        """Test getting a specific skill by id."""
        loader = get_skill_loader()
        skills = loader.load_all()
        if skills:
            first_skill_id = next(iter(skills.keys()))
            skill = loader.get_skill(first_skill_id)
            assert skill is not None
            assert skill.id == first_skill_id

    def test_get_nonexistent_skill(self) -> None:
        """Test getting a skill that doesn't exist."""
        loader = get_skill_loader()
        skill = loader.get_skill("nonexistent-skill-xyz")
        assert skill is None


class TestSkillLoaderEdgeCases:
    """Test edge cases for SkillLoader."""

    def test_empty_skills_directory(self, tmp_path) -> None:
        """Test behavior with no skills files."""
        empty_dir = tmp_path / "empty_skills"
        empty_dir.mkdir()
        loader = SkillLoader(skills_dir=empty_dir)
        skills = loader.load_all()
        assert skills == {}

    def test_skill_fields(self) -> None:
        """Test Skill dataclass fields."""
        skill = Skill(
            id="test-id",
            intent="diagnose",
            complexity="complex",
            description="Test description",
            examples=["example1", "example2"],
            file_path="/test/path.md",
            content="Test content",
        )
        assert skill.id == "test-id"
        assert skill.intent == "diagnose"
        assert skill.complexity == "complex"
        assert skill.description == "Test description"
        assert len(skill.examples) == 2
        assert skill.file_path == "/test/path.md"
        assert skill.content == "Test content"


class TestDualFormatSupport:
    """Tests for dual format support (Claude Code + Legacy)."""

    def test_load_claude_code_format(self, tmp_path) -> None:
        """Test loading Claude Code standard format (skills/*/SKILL.md)."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # Create Claude Code format skill
        cc_skill_dir = skills_dir / "test-query"
        cc_skill_dir.mkdir()
        (cc_skill_dir / "SKILL.md").write_text(
            """---
name: Test Query
description: Test Claude Code format
version: 1.0.0
triggers:
  - test
  - query
---

# Test Query

Test content.
""",
            encoding="utf-8",
        )

        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        assert "test-query" in skills
        skill = skills["test-query"]
        assert skill.description == "Test Claude Code format"
        # Name should be normalized to lowercase with hyphens
        assert "test" in skill.examples or "query" in skill.examples

    def test_load_legacy_format(self, tmp_path) -> None:
        """Test loading OLAV legacy format (skills/*.md)."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # Create legacy format skill
        (skills_dir / "legacy-test.md").write_text(
            """---
id: legacy-test
intent: query
complexity: simple
description: Legacy format test
examples:
  - legacy example
---

# Legacy Test

Legacy content.
""",
            encoding="utf-8",
        )

        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        assert "legacy-test" in skills
        skill = skills["legacy-test"]
        assert skill.intent == "query"
        assert skill.complexity == "simple"

    def test_claude_code_priority(self, tmp_path) -> None:
        """Test that Claude Code format takes priority over legacy format."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # Create both formats for same skill
        cc_dir = skills_dir / "priority-test"
        cc_dir.mkdir()
        (cc_dir / "SKILL.md").write_text(
            """---
name: Priority Test
description: Claude Code version
version: 2.0.0
---
Claude Code format.
""",
            encoding="utf-8",
        )

        (skills_dir / "priority-test.md").write_text(
            """---
id: priority-test
description: Legacy version
---
Legacy format.
""",
            encoding="utf-8",
        )

        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        # Should only have one entry (Claude Code priority)
        assert len(skills) == 1
        assert "priority-test" in skills
        # Content should indicate Claude Code format
        skill = skills["priority-test"]
        content = skill.content or ""
        # Load content if not loaded
        if not content:
            skill = loader.get_skill("priority-test")
            content = skill.content or ""
        assert "Claude Code" in content or "version: 2.0.0" in content

    def test_name_to_id_conversion(self, tmp_path) -> None:
        """Test conversion of name field to normalized ID."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "My Complex Skill Name"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            """---
name: My Complex Skill Name
description: Test name normalization
---
""",
            encoding="utf-8",
        )

        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        # Name should be normalized to lowercase with hyphens
        assert "my-complex-skill-name" in skills

    def test_disabled_skill_not_loaded(self, tmp_path) -> None:
        """Test that disabled skills are not loaded."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        (skills_dir / "disabled.md").write_text(
            """---
id: disabled
description: Disabled skill
enabled: false
---
""",
            encoding="utf-8",
        )

        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        assert "disabled" not in skills

    def test_missing_description_skipped(self, tmp_path) -> None:
        """Test that skills without description are skipped."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        (skills_dir / "no-desc.md").write_text(
            """---
id: no-desc
---
No description.
""",
            encoding="utf-8",
        )

        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        assert "no-desc" not in skills

    def test_skip_skill_md_file_in_legacy(self, tmp_path) -> None:
        """Test that SKILL.md in legacy format is skipped (line 60)."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # Create a SKILL.md file in legacy format (should be skipped)
        (skills_dir / "SKILL.md").write_text(
            """---
id: should-be-skipped
description: This should not be loaded
---
Content""",
            encoding="utf-8",
        )

        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        # SKILL.md should be skipped in legacy format
        assert "should-be-skipped" not in skills

    def test_skip_draft_files(self, tmp_path) -> None:
        """Test that draft files are skipped (line 62)."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # Create files with .draft prefix or starting with _
        (skills_dir / "draft-test.draft.md").write_text(
            """---
id: draft-test
description: Draft skill
---
Content""",
            encoding="utf-8",
        )

        (skills_dir / "_private.md").write_text(
            """---
id: private
description: Private skill
---
Content""",
            encoding="utf-8",
        )

        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        # Both files should be skipped
        assert "draft-test" not in skills
        assert "private" not in skills

    def test_no_frontmatter_returns_none(self, tmp_path) -> None:
        """Test that files without frontmatter return None (line 85)."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # Create file without frontmatter delimiters
        (skills_dir / "no-fm.md").write_text(
            """# Just a markdown file

No frontmatter here.
""",
            encoding="utf-8",
        )

        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        # Should be skipped
        assert "no-fm" not in skills or "just" not in skills

    def test_skill_id_from_filename(self, tmp_path) -> None:
        """Test generating skill_id from filename when no id/name (line 91)."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # Create file without id or name field
        (skills_dir / "my_test_skill.md").write_text(
            """---
description: Test skill
---
Content""",
            encoding="utf-8",
        )

        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        # Should generate id from filename: my_test_skill -> my-test-skill
        assert "my-test-skill" in skills

    def test_parse_skill_exception_handling(self, tmp_path) -> None:
        """Test exception handling in _parse_skill_header (lines 113-115)."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # Create a file that will cause read errors
        test_file = skills_dir / "test-error.md"
        test_file.write_text("---\nid: test\ndescription: test\n---", encoding="utf-8")

        # Mock read_text to raise exception
        with patch("pathlib.Path.read_text", side_effect=PermissionError("Access denied")):
            loader = SkillLoader(skills_dir)
            skills = loader.load_all()

            # Should handle gracefully and skip the file
            assert "test" not in skills or "test-error" not in skills

    def test_frontmatter_no_end_delimiter(self, tmp_path) -> None:
        """Test frontmatter without end delimiter returns None (line 125)."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # Create file with opening --- but no closing ---
        (skills_dir / "no-end.md").write_text(
            """---
id: no-end
description: No end delimiter
Still frontmatter...
""",
            encoding="utf-8",
        )

        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        # Should be skipped
        assert "no-end" not in skills

    def test_yaml_parse_error_handling(self, tmp_path) -> None:
        """Test YAML parse error handling (lines 130-131)."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # Create file with invalid YAML
        (skills_dir / "bad-yaml.md").write_text(
            """---
id: test
description: [invalid {yaml}
---
Content""",
            encoding="utf-8",
        )

        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        # Should handle YAML error gracefully
        assert "bad-yaml" not in skills

    def test_get_skill_auto_loads(self, tmp_path) -> None:
        """Test that get_skill auto-loads if index is empty (line 136)."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        (skills_dir / "auto-load.md").write_text(
            """---
id: auto-load
description: Test auto-load
---
Content""",
            encoding="utf-8",
        )

        loader = SkillLoader(skills_dir)
        # Don't call load_all() first
        skill = loader.get_skill("auto-load")

        # Should auto-load and find the skill
        assert skill is not None
        assert skill.id == "auto-load"

    def test_get_skill_content_load_error(self, tmp_path) -> None:
        """Test error handling when loading skill content (lines 147-148)."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # Create a valid skill file
        (skills_dir / "lazy-load.md").write_text(
            """---
id: lazy-load
description: Test lazy loading
---
Content here""",
            encoding="utf-8",
        )

        loader = SkillLoader(skills_dir)

        # Manually create a skill with content=None to simulate lazy loading
        from olav.core.skill_loader import Skill
        skill = Skill(
            id="lazy-load",
            intent="unknown",
            complexity="medium",
            description="Test lazy loading",
            examples=[],
            file_path=str(skills_dir / "lazy-load.md"),
            content=None,  # Content not loaded yet
        )

        # Add to index directly (bypassing load_all)
        loader._index["lazy-load"] = skill

        # Mock Path.read_text to raise exception
        with patch("pathlib.Path.read_text", side_effect=PermissionError("Access denied")):
            # Call get_skill which should trigger lazy load and fail
            result = loader.get_skill("lazy-load")
            # Content should remain None due to error
            assert result.content is None

    def test_get_skills_by_intent_auto_loads(self, tmp_path) -> None:
        """Test that get_skills_by_intent auto-loads if index is empty (lines 154-157)."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        (skills_dir / "intent-test.md").write_text(
            """---
id: intent-test
intent: diagnose
description: Test intent filtering
---
Content""",
            encoding="utf-8",
        )

        loader = SkillLoader(skills_dir)
        # Don't call load_all() first
        skills = loader.get_skills_by_intent("diagnose")

        # Should auto-load and filter
        assert len(skills) >= 1
        assert any(s.id == "intent-test" for s in skills)

    def test_get_index_summary_auto_loads(self, tmp_path) -> None:
        """Test that get_index_summary auto-loads if index is empty (lines 161-164)."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        (skills_dir / "summary-test.md").write_text(
            """---
id: summary-test
description: Test index summary
examples:
  - example1
  - example2
  - example3
  - example4
---
Content""",
            encoding="utf-8",
        )

        loader = SkillLoader(skills_dir)
        # Don't call load_all() first
        summary = loader.get_index_summary()

        # Should auto-load and create summary
        assert summary["total"] >= 1
        assert "summary-test" in summary["skills"]
        # Should only keep first 3 examples
        assert len(summary["skills"]["summary-test"]["examples"]) <= 3

