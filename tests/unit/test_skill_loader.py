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
