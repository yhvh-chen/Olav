"""
Phase C-2: CLI Commands Enhancement

New commands for OLAV CLI:
- olav config: Configuration management (show, set, validate)
- olav skill: Skill management (list, show, search)
- olav knowledge: Knowledge base operations (list, search, add-solution)
- olav validate: File integrity checks

All commands integrated with the Phase C-1 configuration system.
"""

import json
from pathlib import Path

from config.settings import Settings

# =============================================================================
# Configuration Commands
# =============================================================================


class ConfigCommand:
    """Handle 'olav config' commands for configuration management."""

    def __init__(self, settings: Settings) -> None:
        """Initialize ConfigCommand.

        Args:
            settings: Settings instance from Phase C-1
        """
        self.settings = settings

    def show(self, key: str | None = None) -> str:
        """Show configuration value(s).

        Args:
            key: Specific config key to show (optional)
                - 'llm': LLM configuration
                - 'routing': Skill routing settings
                - 'hitl': HITL approval settings
                - 'diagnosis': Diagnosis parameters
                - 'logging': Logging configuration
                - None: Show all (non-sensitive) settings

        Returns:
            Formatted configuration display
        """
        lines = []
        lines.append("=" * 70)
        lines.append("OLAV Configuration")
        lines.append("=" * 70)

        if not key or key == "llm":
            lines.append("\n[LLM Configuration]")
            lines.append(f"  Model:       {self.settings.llm_model_name}")
            lines.append(f"  Provider:    {self.settings.llm_provider}")
            lines.append(f"  Temperature: {self.settings.llm_temperature}")
            lines.append(f"  Max Tokens:  {self.settings.llm_max_tokens}")

        if not key or key == "routing":
            lines.append("\n[Skill Routing]")
            lines.append(f"  Confidence Threshold: {self.settings.routing.confidence_threshold}")
            lines.append(f"  Fallback Skill:       {self.settings.routing.fallback_skill}")

        if not key or key == "hitl":
            lines.append("\n[Human-in-the-Loop (HITL)]")
            lines.append(
                f"  Approve Write Ops:     {self.settings.hitl.require_approval_for_write}"
            )
            lines.append(
                f"  Approve Skill Updates: {self.settings.hitl.require_approval_for_skill_update}"
            )
            lines.append(f"  Approval Timeout:      {self.settings.hitl.approval_timeout_seconds}s")

        if not key or key == "diagnosis":
            lines.append("\n[Diagnosis Parameters]")
            lines.append(
                f"  Macro Max Confidence:   {self.settings.diagnosis.macro_max_confidence}"
            )
            lines.append(
                f"  Micro Target Confidence: {self.settings.diagnosis.micro_target_confidence}"
            )
            lines.append(
                f"  Max Iterations:          {self.settings.diagnosis.max_diagnosis_iterations}"
            )

        if not key or key == "logging":
            lines.append("\n[Logging]")
            lines.append(f"  Level:        {self.settings.logging_settings.level}")
            lines.append(f"  Audit Enabled: {self.settings.logging_settings.audit_enabled}")

        if not key or key == "skills":
            lines.append("\n[Skills Configuration]")
            enabled = self.settings.enabled_skills
            disabled = self.settings.disabled_skills
            lines.append(f"  Enabled Skills:  {', '.join(enabled) if enabled else '(all)'}")
            lines.append(f"  Disabled Skills: {', '.join(disabled) if disabled else '(none)'}")

        lines.append("\n" + "=" * 70)
        return "\n".join(lines)

    def set(self, key_value: str) -> str:
        """Set configuration value.

        Args:
            key_value: Format: "key=value"
                Examples:
                - llm.model=gpt-4o
                - routing.confidence_threshold=0.7
                - hitl.require_approval_for_write=false

        Returns:
            Status message
        """
        if "=" not in key_value:
            return "Error: Format should be 'key=value' (e.g., llm.model=gpt-4o)"

        key, value = key_value.split("=", 1)
        key = key.strip().lower()
        value = value.strip().lower()

        # Parse boolean values
        if value in ("true", "yes", "1"):
            value = True
        elif value in ("false", "no", "0"):
            value = False
        else:
            # Try to parse as float if it looks like a number
            try:
                if "." in value:
                    value = float(value)
                else:
                    value = int(value)
            except ValueError:
                pass  # Keep as string

        # Apply setting changes
        try:
            if key == "llm.model":
                self.settings.llm_model_name = str(value)  # type: ignore[assignment]
            elif key == "llm.temperature":
                self.settings.llm_temperature = float(value)
            elif key == "routing.confidence_threshold":
                self.settings.routing.confidence_threshold = float(value)
            elif key == "hitl.require_approval_for_write":
                self.settings.hitl.require_approval_for_write = bool(value)
            elif key == "diagnosis.macro_max_confidence":
                self.settings.diagnosis.macro_max_confidence = float(value)
            else:
                return f"Error: Unknown configuration key '{key}'"

            # Save to settings.json
            from config.settings import OLAV_DIR

            self.settings.save_to_json(OLAV_DIR / "settings.json")
            return f"✓ Configuration updated: {key} = {value}"

        except (ValueError, TypeError) as e:
            return f"Error: Invalid value for {key}: {e}"

    def validate(self) -> str:
        """Validate configuration integrity.

        Returns:
            Validation report
        """
        lines = []
        lines.append("Validating OLAV Configuration...")
        lines.append("-" * 50)

        issues = []

        # Check LLM configuration
        if not self.settings.llm_model_name:
            issues.append("❌ LLM model name is empty")
        else:
            lines.append(f"✓ LLM model configured: {self.settings.llm_model_name}")

        if not (0.0 <= self.settings.llm_temperature <= 2.0):
            issues.append(f"❌ LLM temperature out of bounds: {self.settings.llm_temperature}")
        else:
            lines.append(f"✓ LLM temperature valid: {self.settings.llm_temperature}")

        # Check routing configuration
        if not (0.0 <= self.settings.routing.confidence_threshold <= 1.0):
            issues.append(
                f"❌ Confidence threshold out of bounds: {self.settings.routing.confidence_threshold}"
            )
        else:
            lines.append(f"✓ Routing threshold valid: {self.settings.routing.confidence_threshold}")

        # Check HITL timeout
        if not (10 <= self.settings.hitl.approval_timeout_seconds <= 3600):
            issues.append(
                f"❌ HITL timeout out of bounds: {self.settings.hitl.approval_timeout_seconds}"
            )
        else:
            lines.append(f"✓ HITL timeout valid: {self.settings.hitl.approval_timeout_seconds}s")

        # Check settings.json exists
        from config.settings import OLAV_DIR

        settings_file = OLAV_DIR / "settings.json"
        if settings_file.exists():
            lines.append(f"✓ Settings file exists: {settings_file}")
        else:
            lines.append(f"⚠ Settings file not found (using defaults): {settings_file}")

        lines.append("-" * 50)
        if issues:
            lines.extend(issues)
            lines.append(f"\n❌ Validation FAILED with {len(issues)} issue(s)")
        else:
            lines.append("✓ All configuration checks passed")

        return "\n".join(lines)


# =============================================================================
# Skill Commands
# =============================================================================


class SkillCommand:
    """Handle 'olav skill' commands for skill management."""

    def __init__(self, olav_dir: Path | None = None) -> None:
        """Initialize SkillCommand.

        Args:
            olav_dir: Path to .olav directory
        """
        from config.settings import OLAV_DIR

        self.olav_dir = olav_dir or OLAV_DIR
        self.skills_dir = self.olav_dir / "skills"

    def list_skills(self, category: str | None = None) -> str:
        """List available skills.

        Args:
            category: Filter by category (e.g., "inspection")

        Returns:
            Formatted skill list
        """
        if not self.skills_dir.exists():
            return f"Skills directory not found: {self.skills_dir}"

        lines = []
        lines.append("=" * 70)
        lines.append("Available Skills")
        lines.append("=" * 70)

        skills = sorted(
            [f.stem for f in self.skills_dir.glob("*.md") if not f.stem.startswith("_")]
        )

        if not skills:
            return "No skills found"

        for skill in skills:
            if category and category not in skill:
                continue
            lines.append(f"  • {skill}")

        lines.append("=" * 70)
        lines.append(f"Total: {len(skills)} skill(s)")
        return "\n".join(lines)

    def show_skill(self, skill_name: str) -> str:
        """Show skill details.

        Args:
            skill_name: Skill name (without .md extension)

        Returns:
            Skill content or error message
        """
        skill_file = self.skills_dir / f"{skill_name}.md"

        if not skill_file.exists():
            return f"Skill not found: {skill_name}"

        try:
            content = skill_file.read_text(encoding="utf-8")
            # Show first 50 lines
            lines = content.split("\n")[:50]
            return (
                "\n".join(lines)
                + f"\n\n... (use 'cat .olav/skills/{skill_name}.md' for full content)"
            )
        except Exception as e:
            return f"Error reading skill: {e}"

    def search_skills(self, query: str) -> str:
        """Search skills by name or description.

        Args:
            query: Search query (case-insensitive)

        Returns:
            Matching skills
        """
        if not self.skills_dir.exists():
            return "Skills directory not found"

        query = query.lower()
        lines = []
        lines.append(f"Searching for skills matching '{query}'...")
        lines.append("-" * 50)

        matching = []
        for skill_file in self.skills_dir.glob("*.md"):
            if skill_file.stem.startswith("_"):
                continue

            if query in skill_file.stem.lower():
                matching.append(skill_file.stem)

        if matching:
            for skill in matching:
                lines.append(f"  ✓ {skill}")
            lines.append(f"\nFound {len(matching)} skill(s)")
        else:
            lines.append("No matching skills found")

        return "\n".join(lines)


# =============================================================================
# Knowledge Commands
# =============================================================================


class KnowledgeCommand:
    """Handle 'olav knowledge' commands for knowledge base operations."""

    def __init__(self, olav_dir: Path | None = None) -> None:
        """Initialize KnowledgeCommand.

        Args:
            olav_dir: Path to .olav directory
        """
        from config.settings import OLAV_DIR

        self.olav_dir = olav_dir or OLAV_DIR
        self.knowledge_dir = self.olav_dir / "knowledge"

    def list_knowledge(self, category: str | None = None) -> str:
        """List knowledge base items.

        Args:
            category: Filter by category (e.g., "solutions")

        Returns:
            Formatted knowledge list
        """
        if not self.knowledge_dir.exists():
            return f"Knowledge directory not found: {self.knowledge_dir}"

        lines = []
        lines.append("=" * 70)
        lines.append("Knowledge Base")
        lines.append("=" * 70)

        # List root level knowledge files
        root_files = sorted([f.stem for f in self.knowledge_dir.glob("*.md")])
        if root_files:
            lines.append("\n[Root Knowledge]")
            for file in root_files:
                lines.append(f"  • {file}")

        # List solutions
        solutions_dir = self.knowledge_dir / "solutions"
        solutions: list[str] = []
        if solutions_dir.exists():
            solutions = sorted([f.stem for f in solutions_dir.glob("*.md")])
            if solutions:
                lines.append("\n[Solutions]")
                for file in solutions:
                    lines.append(f"  • {file}")

        lines.append("\n" + "=" * 70)
        total = len(root_files) + len(solutions)
        lines.append(f"Total: {total} item(s)")
        return "\n".join(lines)

    def search_knowledge(self, query: str) -> str:
        """Search knowledge base.

        Args:
            query: Search query

        Returns:
            Search results
        """
        if not self.knowledge_dir.exists():
            return "Knowledge directory not found"

        query = query.lower()
        lines = []
        lines.append(f"Searching knowledge base for '{query}'...")
        lines.append("-" * 50)

        matching = []
        for kb_file in self.knowledge_dir.rglob("*.md"):
            if kb_file.stem.startswith("_"):
                continue

            # Check filename match
            if query in kb_file.stem.lower():
                matching.append(str(kb_file.relative_to(self.knowledge_dir)))

        if matching:
            for item in matching:
                lines.append(f"  ✓ {item}")
            lines.append(f"\nFound {len(matching)} item(s)")
        else:
            lines.append("No matching knowledge items found")

        return "\n".join(lines)

    def add_solution(self, name: str) -> str:
        """Add a new solution to knowledge base.

        Args:
            name: Solution name

        Returns:
            Status message
        """
        solutions_dir = self.knowledge_dir / "solutions"
        solutions_dir.mkdir(parents=True, exist_ok=True)

        solution_file = solutions_dir / f"{name}.md"

        if solution_file.exists():
            return f"Solution already exists: {name}"

        # Template for new solution
        template = """---
id: {}
category: network-troubleshooting
tags: [add, appropriate, tags]
severity: medium
---

# {}

## Problem Description
Describe the problem that this solution addresses.

## Root Cause
Explain the root cause of the issue.

## Solution
Provide step-by-step solution.

## Verification
How to verify that the solution worked.

## Prevention
How to prevent this issue in the future.

## References
- Link to relevant documentation
""".format(name, name.replace("-", " ").title())

        try:
            solution_file.write_text(template, encoding="utf-8")
            return f"✓ New solution created: {solution_file}"
        except Exception as e:
            return f"Error creating solution: {e}"


# =============================================================================
# Validate Commands
# =============================================================================


class ValidateCommand:
    """Handle 'olav validate' commands for file integrity checks."""

    def __init__(self, olav_dir: Path | None = None) -> None:
        """Initialize ValidateCommand.

        Args:
            olav_dir: Path to .olav directory
        """
        from config.settings import OLAV_DIR

        self.olav_dir = olav_dir or OLAV_DIR

    def validate_all(self) -> str:
        """Validate all OLAV files.

        Returns:
            Comprehensive validation report
        """
        lines = []
        lines.append("=" * 70)
        lines.append("OLAV File Integrity Validation")
        lines.append("=" * 70)

        issues = []

        # Check core files
        core_files = {
            "OLAV.md": self.olav_dir.parent / "OLAV.md",
        }

        lines.append("\n[Core Files]")
        for name, path in core_files.items():
            if path.exists():
                lines.append(f"  ✓ {name}")
            else:
                lines.append(f"  ❌ {name} (missing)")
                issues.append(f"Missing core file: {name}")

        # Check directories
        directories = {
            "skills": self.olav_dir / "skills",
            "knowledge": self.olav_dir / "knowledge",
        }

        lines.append("\n[Directories]")
        for name, path in directories.items():
            if path.exists():
                count = len(list(path.glob("*.md")))
                lines.append(f"  ✓ {name}/ ({count} files)")
            else:
                lines.append(f"  ⚠ {name}/ (not found)")

        # Check settings.json
        lines.append("\n[Configuration]")
        settings_file = self.olav_dir / "settings.json"
        if settings_file.exists():
            try:
                json.loads(settings_file.read_text())
                lines.append("  ✓ settings.json (valid JSON)")
            except json.JSONDecodeError as e:
                lines.append(f"  ❌ settings.json (invalid JSON: {e})")
                issues.append(f"Invalid JSON in settings.json: {e}")
        else:
            lines.append("  ⚠ settings.json (not found, using defaults)")

        lines.append("\n" + "=" * 70)
        if issues:
            lines.extend(issues)
            lines.append(f"\n⚠ Found {len(issues)} issue(s)")
        else:
            lines.append("✓ All validation checks passed")

        return "\n".join(lines)


# =============================================================================
# Command Factory
# =============================================================================


class CLICommandFactory:
    """Factory for creating CLI command handlers."""

    def __init__(self, settings: Settings, olav_dir: Path | None = None) -> None:
        """Initialize command factory.

        Args:
            settings: Settings instance
            olav_dir: Path to .olav directory (optional)
        """
        self.settings = settings
        from config.settings import OLAV_DIR

        self.olav_dir = olav_dir or OLAV_DIR

    def create_config_command(self) -> ConfigCommand:
        """Create ConfigCommand instance."""
        return ConfigCommand(self.settings)

    def create_skill_command(self) -> SkillCommand:
        """Create SkillCommand instance."""
        return SkillCommand(self.olav_dir)

    def create_knowledge_command(self) -> KnowledgeCommand:
        """Create KnowledgeCommand instance."""
        return KnowledgeCommand(self.olav_dir)

    def create_validate_command(self) -> ValidateCommand:
        """Create ValidateCommand instance."""
        return ValidateCommand(self.olav_dir)
