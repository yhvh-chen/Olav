#!/usr/bin/env python3
"""
Phase C-3: Claude Code Compatibility Verification Script

Validates that the .claude/ directory structure is compatible with Claude Code
and reports any issues that might prevent proper operation.

Usage:
    uv run scripts/verify_claude_compat.py [--detailed] [--fix]
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Tuple
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ClaudeCompatibilityValidator:
    """Validates Claude Code compatibility."""

    def __init__(self, claude_dir: Path = None, project_root: Path = None):
        """Initialize validator.
        
        Args:
            claude_dir: Path to .claude directory
            project_root: Root project directory
        """
        self.project_root = project_root or Path.cwd()
        self.claude_dir = claude_dir or (self.project_root / ".claude")
        self.issues: List[Dict[str, str]] = []
        self.warnings: List[Dict[str, str]] = []
        self.successes: List[str] = []

    def add_issue(self, category: str, message: str, severity: str = "ERROR") -> None:
        """Add validation issue.
        
        Args:
            category: Issue category
            message: Issue description
            severity: ERROR, WARNING, or INFO
        """
        self.issues.append({
            "category": category,
            "message": message,
            "severity": severity
        })

    def add_warning(self, message: str) -> None:
        """Add warning.
        
        Args:
            message: Warning message
        """
        self.warnings.append({"message": message})

    def add_success(self, message: str) -> None:
        """Add success message.
        
        Args:
            message: Success description
        """
        self.successes.append(message)

    def validate_directory_exists(self) -> bool:
        """Validate .claude directory exists.
        
        Returns:
            True if exists, False otherwise
        """
        if not self.claude_dir.exists():
            self.add_issue(
                "Structure",
                f".claude directory not found at {self.claude_dir}",
                "ERROR"
            )
            return False
        
        self.add_success(".claude directory exists")
        return True

    def validate_required_directories(self) -> bool:
        """Validate presence of required subdirectories.
        
        Returns:
            True if all required directories exist
        """
        required = {
            "skills": "Skill definitions",
            "knowledge": "Knowledge base",
        }

        all_exist = True
        for dir_name, description in required.items():
            dir_path = self.claude_dir / dir_name
            if dir_path.exists():
                file_count = len(list(dir_path.glob("*.md")))
                self.add_success(f"✓ {dir_name}/ directory ({file_count} files)")
            else:
                self.add_issue(
                    "Structure",
                    f"Missing required directory: {dir_name}/ ({description})",
                    "ERROR"
                )
                all_exist = False

        return all_exist

    def validate_core_files(self) -> bool:
        """Validate presence and format of core files.
        
        Returns:
            True if all core files are valid
        """
        files_to_check = {
            "CLAUDE.md": "Core configuration",
            "settings.json": "Configuration settings",
        }

        all_valid = True
        for filename, description in files_to_check.items():
            file_path = self.claude_dir / filename
            
            if not file_path.exists():
                self.add_issue(
                    "CoreFiles",
                    f"Missing core file: {filename} ({description})",
                    "ERROR"
                )
                all_valid = False
                continue

            # Validate JSON files
            if filename.endswith(".json"):
                try:
                    json.loads(file_path.read_text(encoding="utf-8"))
                    self.add_success(f"✓ {filename} (valid JSON)")
                except json.JSONDecodeError as e:
                    self.add_issue(
                        "CoreFiles",
                        f"Invalid JSON in {filename}: {e}",
                        "ERROR"
                    )
                    all_valid = False
            else:
                # Validate Markdown files
                content = file_path.read_text(encoding="utf-8")
                if content.strip():
                    self.add_success(f"✓ {filename}")
                else:
                    self.add_issue(
                        "CoreFiles",
                        f"{filename} is empty",
                        "WARNING"
                    )

        return all_valid

    def validate_markdown_format(self) -> bool:
        """Validate Markdown files have proper format.
        
        Returns:
            True if all Markdown files are valid
        """
        markdown_patterns = [
            (self.claude_dir / "skills", "Skills"),
            (self.claude_dir / "knowledge", "Knowledge"),
        ]

        all_valid = True
        total_files = 0
        total_issues = 0

        for dir_path, category in markdown_patterns:
            if not dir_path.exists():
                continue

            md_files = sorted(dir_path.glob("*.md"))
            total_files += len(md_files)

            for md_file in md_files:
                try:
                    content = md_file.read_text(encoding="utf-8")
                    
                    # Check for heading
                    if not content.strip().startswith("#"):
                        self.add_issue(
                            "Markdown",
                            f"{category}/{md_file.name}: Missing top-level heading",
                            "WARNING"
                        )
                        total_issues += 1
                    
                    # Check for excessive length
                    lines = content.split("\n")
                    if len(lines) > 10000:
                        self.add_warning(
                            f"{category}/{md_file.name}: Very long file "
                            f"({len(lines)} lines)"
                        )
                    
                except Exception as e:
                    self.add_issue(
                        "Markdown",
                        f"{category}/{md_file.name}: {e}",
                        "ERROR"
                    )
                    total_issues += 1
                    all_valid = False

        if total_issues == 0:
            self.add_success(f"✓ Markdown validation passed ({total_files} files)")
        
        return all_valid

    def validate_settings_json_schema(self) -> bool:
        """Validate settings.json has required structure.
        
        Returns:
            True if settings.json is valid
        """
        settings_file = self.claude_dir / "settings.json"
        
        if not settings_file.exists():
            return True  # Optional file

        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
            
            # Check for common expected keys
            expected_keys = ["llmModelName", "llmTemperature"]
            found_keys = [k for k in expected_keys if k in settings]
            
            if found_keys:
                self.add_success(
                    f"✓ settings.json has expected keys: {', '.join(found_keys)}"
                )
            else:
                self.add_warning("settings.json missing common configuration keys")
            
            return True
        except json.JSONDecodeError as e:
            self.add_issue(
                "Configuration",
                f"Invalid JSON in settings.json: {e}",
                "ERROR"
            )
            return False

    def validate_no_olav_references(self) -> bool:
        """Check that no .olav references remain (migration should replace with .claude).
        
        Returns:
            True if no .olav references found
        """
        patterns_to_check = [
            (self.claude_dir / "CLAUDE.md", "CLAUDE.md"),
            (self.claude_dir / "settings.json", "settings.json"),
        ]

        all_valid = True
        for file_path, name in patterns_to_check:
            if not file_path.exists():
                continue

            content = file_path.read_text(encoding="utf-8")
            if ".olav" in content:
                self.add_issue(
                    "Migration",
                    f"{name} still contains .olav references (should be .claude)",
                    "WARNING"
                )
                all_valid = False

        if all_valid:
            self.add_success("✓ No .olav references found")
        
        return all_valid

    def generate_compatibility_report(self) -> Dict[str, any]:
        """Generate compatibility report.
        
        Returns:
            Report dictionary
        """
        return {
            "compatible": len(self.issues) == 0,
            "warnings": len(self.warnings),
            "successes": len(self.successes),
            "issues": self.issues,
            "details": {
                "successful_checks": self.successes,
                "warnings": self.warnings,
                "failed_checks": [i for i in self.issues if i["severity"] == "ERROR"]
            }
        }

    def validate(self) -> Tuple[bool, Dict]:
        """Run all validation checks.
        
        Returns:
            Tuple of (success: bool, report: Dict)
        """
        logger.info("=" * 70)
        logger.info("Claude Code Compatibility Validation")
        logger.info("=" * 70)

        # Run all validation checks
        if not self.validate_directory_exists():
            report = self.generate_compatibility_report()
            return False, report

        self.validate_required_directories()
        self.validate_core_files()
        self.validate_markdown_format()
        self.validate_settings_json_schema()
        self.validate_no_olav_references()

        report = self.generate_compatibility_report()
        return report["compatible"], report

    def print_report(self, success: bool, report: Dict) -> None:
        """Print validation report.
        
        Args:
            success: Whether validation passed
            report: Validation report
        """
        status = "✓ COMPATIBLE" if success else "❌ NOT COMPATIBLE"
        logger.info(f"\n{status}")
        
        logger.info(f"\nSuccessful checks: {report['successes']}")
        logger.info(f"Warnings: {report['warnings']}")
        logger.info(f"Failed checks: {len(report['details']['failed_checks'])}")

        if report['successes'] > 0:
            logger.info("\n✓ Successful Checks:")
            for check in report['details']['successful_checks']:
                logger.info(f"  {check}")

        if report['details']['failed_checks']:
            logger.info("\n❌ Failed Checks:")
            for issue in report['details']['failed_checks']:
                logger.info(f"  {issue['category']}: {issue['message']}")

        if report['details']['warnings']:
            logger.info("\n⚠ Warnings:")
            for warning in report['details']['warnings']:
                logger.info(f"  {warning['message']}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate Claude Code compatibility"
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed validation report"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to fix common issues"
    )

    args = parser.parse_args()

    validator = ClaudeCompatibilityValidator()
    success, report = validator.validate()
    validator.print_report(success, report)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
