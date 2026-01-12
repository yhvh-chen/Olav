"""Inspection Skills Loader for OLAV v0.8.

⚠️ DEPRECATED: This module is being phased out in favor of the new architecture where
the main agent uses search_capabilities() to discover platform-specific commands dynamically.

The old approach (inspection templates in .olav/skills/inspection/) has been replaced with:
1. Cognitive Skills in .olav/skills/*/SKILL.md (define WHAT to check, not HOW)
2. Capabilities DB (stores platform-specific commands loaded from .olav/imports/commands/)
3. search_capabilities(query, platform) tool (agent discovers commands at runtime)

This module is kept for backward compatibility only and may be removed in future versions.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SkillParameter:
    """Represents a single parameter in a skill definition."""

    name: str
    type: str
    default: Any | None = None
    required: bool = True
    description: str = ""


@dataclass
class SkillDefinition:
    """Represents a complete inspection skill."""

    filename: str
    name: str
    target: str
    parameters: list[SkillParameter]
    steps: list[str]
    acceptance_criteria: dict[str, list[str]]
    troubleshooting: dict[str, list[str]]
    platform_support: list[str]
    estimated_runtime: str
    raw_content: str


class InspectionSkillLoader:
    """Load and parse inspection skills from .olav/skills/inspection/ directory."""

    def __init__(self, skills_dir: Path | None = None) -> None:
        """Initialize skill loader.

        Args:
            skills_dir: Path to skills directory. If None, uses .olav/skills/inspection/
                       relative to project root.
        """
        if skills_dir is None:
            # Find project root by looking for pyproject.toml
            current = Path.cwd()
            while current != current.parent:
                if (current / "pyproject.toml").exists():
                    skills_dir = current / ".olav" / "skills" / "inspection"
                    break
                current = current.parent
            else:
                raise ValueError("Could not find project root. Pass skills_dir explicitly.")

        self.skills_dir = Path(skills_dir)
        if not self.skills_dir.exists():
            logger.warning(f"Skills directory does not exist: {self.skills_dir}")
            self.skills_dir.mkdir(parents=True, exist_ok=True)

    def discover_skills(self) -> list[Path]:
        """Discover all skill definition files.

        Returns:
            List of paths to .md files in skills directory (excluding README.md)
        """
        skill_files = []
        for md_file in self.skills_dir.glob("*.md"):
            if md_file.name != "README.md":
                skill_files.append(md_file)
        return sorted(skill_files)

    def load_skill(self, skill_path: Path) -> SkillDefinition | None:
        """Parse a single skill definition file.

        Args:
            skill_path: Path to skill .md file

        Returns:
            SkillDefinition if valid, None if parsing failed
        """
        try:
            content = skill_path.read_text(encoding="utf-8")
            return self._parse_skill_content(content, skill_path.name)
        except Exception as e:
            logger.error(f"Failed to load skill {skill_path.name}: {e}")
            return None

    def load_all_skills(self) -> dict[str, SkillDefinition]:
        """Load all available inspection skills.

        Returns:
            Dictionary mapping skill name to SkillDefinition
        """
        skills = {}
        for skill_path in self.discover_skills():
            skill = self.load_skill(skill_path)
            if skill:
                # Use filename without extension as key
                skill_key = skill_path.stem
                skills[skill_key] = skill
                logger.info(f"✅ Loaded skill: {skill_key} ({skill.name})")
        return skills

    def _parse_skill_content(self, content: str, filename: str) -> SkillDefinition | None:
        """Parse Markdown skill definition content.

        Args:
            content: Raw Markdown content of skill file
            filename: Filename for reference

        Returns:
            SkillDefinition or None if parsing failed
        """
        # Extract main title (skill name)
        title_match = re.search(r"^# (.+?)(?:\s*\(|$)", content, re.MULTILINE)
        if not title_match:
            logger.error(f"No title found in {filename}")
            return None

        name = title_match.group(1).strip()

        # Extract target (检查目标)
        target_match = re.search(
            r"## 检查目标\s*\n(.*?)(?=\n##|\Z)",
            content,
            re.DOTALL,
        )
        target = target_match.group(1).strip() if target_match else ""

        # Extract parameters table
        parameters = self._extract_parameters(content)

        # Extract execution steps
        steps = self._extract_steps(content)

        # Extract acceptance criteria
        acceptance_criteria = self._extract_acceptance_criteria(content)

        # Extract troubleshooting
        troubleshooting = self._extract_troubleshooting(content)

        # Extract platform support
        platform_support = self._extract_platform_support(content)

        # Extract estimated runtime
        runtime_match = re.search(r"Estimated Runtime[:\s]*(.+?)(?:\n|$)", content, re.IGNORECASE)
        estimated_runtime = runtime_match.group(1).strip() if runtime_match else "Unknown"

        return SkillDefinition(
            filename=filename,
            name=name,
            target=target,
            parameters=parameters,
            steps=steps,
            acceptance_criteria=acceptance_criteria,
            troubleshooting=troubleshooting,
            platform_support=platform_support,
            estimated_runtime=estimated_runtime,
            raw_content=content,
        )

    def _extract_parameters(self, content: str) -> list[SkillParameter]:
        """Extract parameter definitions from skill content.

        Looks for a parameters table with columns: 参数, 类型, 默认值, 说明

        Args:
            content: Raw Markdown content

        Returns:
            List of SkillParameter objects
        """
        parameters = []

        # Find parameters table
        table_match = re.search(
            r"## 巡检参数\s*\n.*?\n\|.*?\n\|-+\|.*?\|.*?\|(.*?)(?=\n## |\Z)",
            content,
            re.DOTALL,
        )

        if not table_match:
            return parameters

        table_content = table_match.group(1)
        rows = [line.strip() for line in table_content.split("\n") if line.strip()]

        for row in rows:
            cells = [cell.strip() for cell in row.split("|") if cell.strip()]
            if len(cells) >= 4:
                param = SkillParameter(
                    name=cells[0].strip("`"),
                    type=cells[1],
                    default=(None if cells[2].lower() in ("(required)", "required") else cells[2]),
                    required=cells[2].lower() in ("(required)", "required"),
                    description=cells[3] if len(cells) > 3 else "",
                )
                parameters.append(param)

        return parameters

    def _extract_steps(self, content: str) -> list[str]:
        """Extract execution steps from skill content.

        Args:
            content: Raw Markdown content

        Returns:
            List of step descriptions
        """
        steps = []

        # Find steps section
        steps_match = re.search(
            r"## 执行步骤\s*\n(.*?)(?=\n## |\Z)",
            content,
            re.DOTALL,
        )

        if not steps_match:
            return steps

        steps_content = steps_match.group(1)
        # Extract "### Step N:" entries
        step_headers = re.findall(r"### Step \d+[:\s]+(.+?)(?=\n###|\Z)", steps_content, re.DOTALL)

        for step_header in step_headers:
            # Get first line (title)
            first_line = step_header.split("\n")[0].strip()
            steps.append(first_line)

        return steps

    def _extract_acceptance_criteria(self, content: str) -> dict[str, list[str]]:
        """Extract acceptance criteria (PASS/WARNING/FAIL).

        Args:
            content: Raw Markdown content

        Returns:
            Dictionary with keys: 'pass', 'warning', 'fail'
        """
        criteria = {"pass": [], "warning": [], "fail": []}

        # Find acceptance criteria section
        criteria_match = re.search(
            r"## 验收标准\s*\n(.*?)(?=\n## |\Z)",
            content,
            re.DOTALL,
        )

        if not criteria_match:
            return criteria

        criteria_content = criteria_match.group(1)

        # Extract PASS conditions
        pass_match = re.search(
            r"###?\s*✅\s*PASS\s*条件(.*?)(?=\n###|$)",
            criteria_content,
            re.DOTALL | re.IGNORECASE,
        )
        if pass_match:
            bullets = re.findall(
                r"^[-*]\s+(.+?)$",
                pass_match.group(1),
                re.MULTILINE,
            )
            criteria["pass"] = bullets

        # Extract WARNING conditions
        warn_match = re.search(
            r"###?\s*⚠️\s*WARNING\s*条件(.*?)(?=\n###|$)",
            criteria_content,
            re.DOTALL | re.IGNORECASE,
        )
        if warn_match:
            bullets = re.findall(
                r"^[-*]\s+(.+?)$",
                warn_match.group(1),
                re.MULTILINE,
            )
            criteria["warning"] = bullets

        # Extract FAIL conditions
        fail_match = re.search(
            r"###?\s*❌\s*FAIL\s*条件(.*?)(?=\n###|$)",
            criteria_content,
            re.DOTALL | re.IGNORECASE,
        )
        if fail_match:
            bullets = re.findall(
                r"^[-*]\s+(.+?)$",
                fail_match.group(1),
                re.MULTILINE,
            )
            criteria["fail"] = bullets

        return criteria

    def _extract_troubleshooting(self, content: str) -> dict[str, list[str]]:
        """Extract troubleshooting section.

        Args:
            content: Raw Markdown content

        Returns:
            Dictionary mapping issue names to solutions
        """
        troubleshooting = {}

        # Find troubleshooting section
        ts_match = re.search(
            r"## 故障排查\s*\n(.*?)(?=\n## |\Z)",
            content,
            re.DOTALL,
        )

        if not ts_match:
            return troubleshooting

        ts_content = ts_match.group(1)

        # Extract problem/solution pairs
        problems = re.findall(
            r"### 问题[:\s]*(.+?)(?=\n###|\Z)",
            ts_content,
            re.DOTALL,
        )

        for problem in problems:
            lines = problem.split("\n")
            if lines:
                title = lines[0].strip()
                solutions = [
                    line.strip() for line in lines[1:] if line.strip() and not line.startswith("#")
                ]
                troubleshooting[title] = solutions

        return troubleshooting

    def _extract_platform_support(self, content: str) -> list[str]:
        """Extract supported platforms from Integration Notes.

        Args:
            content: Raw Markdown content

        Returns:
            List of supported platforms
        """
        platforms = []

        # Find Integration Notes section
        notes_match = re.search(
            r"## Integration Notes\s*\n(.*?)(?=\n## |\n---|$)",
            content,
            re.DOTALL,
        )

        if not notes_match:
            return platforms

        notes_content = notes_match.group(1)

        # Find Device Support line
        device_match = re.search(
            r"Device Support[:\s]*(.+?)(?:\n|,|$)",
            notes_content,
        )

        if device_match:
            devices_str = device_match.group(1)
            # Split by comma and clean up
            platforms = [p.strip() for p in devices_str.split(",") if p.strip()]

        return platforms

    def get_skill_summary(self, skill: SkillDefinition) -> str:
        """Generate a human-readable summary of a skill.

        Args:
            skill: SkillDefinition to summarize

        Returns:
            Formatted summary string
        """
        summary = f"""
=== Inspection Skill: {skill.name} ===
File: {skill.filename}
Target: {skill.target[:100]}...

Parameters: {len(skill.parameters)}
  - Required: {sum(1 for p in skill.parameters if p.required)}
  - Optional: {sum(1 for p in skill.parameters if not p.required)}

Execution Steps: {len(skill.steps)}
Platforms: {", ".join(skill.platform_support)}
Runtime: {skill.estimated_runtime}

Acceptance Criteria:
  - PASS: {len(skill.acceptance_criteria.get("pass", []))} conditions
  - WARNING: {len(skill.acceptance_criteria.get("warning", []))} conditions
  - FAIL: {len(skill.acceptance_criteria.get("fail", []))} conditions
"""
        return summary.strip()


# Example usage for testing
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    loader = InspectionSkillLoader()
    skills = loader.load_all_skills()

    if skills:
        print(f"\n✅ Loaded {len(skills)} skill(s):\n")
        for _skill_name, skill in skills.items():
            print(loader.get_skill_summary(skill))
            print()
    else:
        print("⚠️ No skills found")
