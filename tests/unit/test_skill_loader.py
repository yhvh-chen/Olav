"""Unit tests for Phase 2: Skill Loader.

Tests the skill loading functionality from .olav/skills/*.md files.
"""

from pathlib import Path
from unittest.mock import patch

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

    def test_empty_skills_directory(self) -> None:
        """Test behavior with no skills files."""
        with patch.object(Path, "glob", return_value=[]):
            loader = SkillLoader(skills_dir=Path("/fake/path"))
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
