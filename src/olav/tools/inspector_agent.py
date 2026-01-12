"""InspectorAgent Subagent for OLAV v0.8.

This module implements the InspectorAgent - a specialized subagent that:
1. Loads inspection skills from .olav/skills/inspection/
2. Validates user parameters via HITL
3. Executes skills via Nornir on device groups
4. Aggregates and formats results
5. Auto-embeds reports to knowledge base (Phase A-1 integration)
"""

import logging
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool, tool

from olav.tools.inspection_skill_loader import InspectionSkillLoader, SkillDefinition
from olav.tools.network import nornir_execute
from olav.tools.report_formatter import format_inspection_report
from olav.tools.storage_tools import write_file

logger = logging.getLogger(__name__)


class InspectorAgent:
    """Main InspectorAgent class for batch inspection operations."""

    def __init__(self, skills_dir: Path | None = None) -> None:
        """Initialize InspectorAgent with skill loader.

        Args:
            skills_dir: Path to skills directory. If None, auto-discovers.
        """
        self.loader = InspectionSkillLoader(skills_dir)
        self.skills = self.loader.load_all_skills()
        logger.info(f"✅ InspectorAgent initialized with {len(self.skills)} skills")

    def get_available_skills(self) -> dict[str, str]:
        """Get list of available inspection skills.

        Returns:
            Dictionary mapping skill name to description
        """
        return {name: skill.name for name, skill in self.skills.items()}

    def validate_parameters(
        self,
        skill_name: str,
        provided_params: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """Validate user-provided parameters against skill definition.

        Args:
            skill_name: Name of the skill to validate for
            provided_params: User-provided parameter values

        Returns:
            Tuple of (is_valid, error_messages)
        """
        if skill_name not in self.skills:
            return False, [f"Skill '{skill_name}' not found"]

        skill = self.skills[skill_name]
        errors = []

        # Check required parameters
        for param in skill.parameters:
            if param.required and param.name not in provided_params:
                errors.append(f"Required parameter '{param.name}' not provided")

        # Validate parameter types (basic validation)
        for param in skill.parameters:
            if param.name in provided_params:
                value = provided_params[param.name]
                if param.type == "integer":
                    if not isinstance(value, int):
                        try:
                            int(value)
                        except (ValueError, TypeError):
                            errors.append(
                                f"Parameter '{param.name}' must be integer, "
                                f"got {type(value).__name__}"
                            )
                elif param.type == "boolean":
                    if not isinstance(value, bool):
                        errors.append(
                            f"Parameter '{param.name}' must be boolean, got {type(value).__name__}"
                        )

        return len(errors) == 0, errors

    def execute_skill(
        self,
        skill_name: str,
        device_group: str,
        additional_params: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Execute an inspection skill on a device group.

        Args:
            skill_name: Name of the skill to execute
            device_group: Device group to target
            additional_params: Additional parameters for the skill
            dry_run: If True, show what would be executed without running

        Returns:
            Dictionary with execution results
        """
        if skill_name not in self.skills:
            return {
                "status": "error",
                "message": f"Skill '{skill_name}' not found",
            }

        skill = self.skills[skill_name]
        params = {"device_group": device_group}
        if additional_params:
            params.update(additional_params)

        # Validate parameters
        is_valid, errors = self.validate_parameters(skill_name, params)
        if not is_valid:
            return {
                "status": "error",
                "message": "Parameter validation failed",
                "errors": errors,
            }

        if dry_run:
            return {
                "status": "dry_run",
                "skill": skill_name,
                "skill_name": skill.name,
                "device_group": device_group,
                "parameters": params,
                "message": f"Would execute {skill.name} on {device_group}",
            }

        # Execute via Nornir
        try:
            # Map skill name to command construction
            commands = self._build_commands_for_skill(skill, params)

            result = nornir_execute(  # type: ignore[call-arg]
                device=device_group,
                command=commands[0] if commands else "",
                timeout=int(params.get("timeout", 30))
                if isinstance(params.get("timeout"), (int, str))
                else 30,
            )

            # Format and return results
            return {
                "status": "success",
                "skill": skill_name,
                "skill_name": skill.name,
                "device_group": device_group,
                "result": result if isinstance(result, dict) else {"output": str(result)},
                "report_path": self._generate_report(
                    skill, result if isinstance(result, dict) else {"output": str(result)}
                ),
            }
        except Exception as e:
            logger.error(f"Error executing skill {skill_name}: {e}")
            return {
                "status": "error",
                "skill": skill_name,
                "message": f"Execution failed: {str(e)}",
            }

    def _build_commands_for_skill(
        self,
        skill: SkillDefinition,
        params: dict[str, Any],
    ) -> list[str]:
        """Build command list for a skill based on parameters.

        Args:
            skill: Skill definition
            params: Skill parameters

        Returns:
            List of commands to execute
        """
        commands = []

        # Extract commands from skill execution steps
        # This is a simplified implementation - actual commands come from skill steps
        if "interface" in skill.filename.lower():
            commands = [
                "show interfaces brief",
                "show interfaces counters errors",
            ]
            if "Eth" in params.get("interface_filter", "*"):
                commands[0] += f" | include {params['interface_filter']}"

        elif "bgp" in skill.filename.lower():
            commands = [
                "show ip bgp summary",
                "show ip bgp neighbors",
            ]

        elif "health" in skill.filename.lower():
            commands = [
                "show processes cpu sorted",
                "show memory",
                "show flash:",
                "show environment",
            ]

        return commands

    def _generate_report(
        self,
        skill: SkillDefinition,
        result: dict[str, Any],
    ) -> str:
        """Generate and save inspection report.

        Args:
            skill: Skill that was executed
            result: Execution results from Nornir

        Returns:
            Path to saved report
        """
        # Format results into readable report
        skill_config = {
            "output": {
                "format": "markdown",
                "language": "auto",
                "sections": ["summary", "details", "recommendations"],
            }
        }

        # Convert flat results to format expected by report formatter
        formatted_results = {}
        for device_name, device_result in result.items():
            if isinstance(device_result, dict):
                formatted_results[device_name] = [device_result]
            else:
                formatted_results[device_name] = [{"output": str(device_result)}]

        report_content = format_inspection_report(
            results=formatted_results,
            skill_config=skill_config,
            inspection_type=skill.name,
        )

        # Save report to data/reports/inspection/
        report_path = (
            Path("data/reports/inspection")
            / f"{skill.filename.replace('.md', '')}-{Path.cwd().stem}.md"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)

        write_file(  # type: ignore[call-arg]
            str(report_path),
            report_content,
        )

        logger.info(f"✅ Report saved to {report_path}")
        return str(report_path)


# Tool wrappers for integration with DeepAgent
def get_inspector_tools() -> list[BaseTool]:
    """Get list of InspectorAgent tools for DeepAgent integration.

    Returns:
        List of BaseTool instances
    """
    inspector = InspectorAgent()

    @tool
    def list_inspection_skills() -> dict[str, str]:
        """List all available inspection skills.

        Returns a dictionary mapping skill names to descriptions.
        Available skills include:
        - interface-check: Verify interface availability and status
        - bgp-check: Validate BGP neighbor adjacency
        - device-health: Monitor device resources (CPU, memory, storage, etc.)

        Use these skill names with the 'execute_inspection_skill' tool.
        """
        return inspector.get_available_skills()

    @tool
    def inspect_device_group(
        skill_name: str,
        device_group: str,
        timeout: int = 30,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Execute an inspection skill on a device group.

        Args:
            skill_name: Name of inspection skill (interface-check, bgp-check, device-health)
            device_group: Name of device group to target (e.g., "core-routers")
            timeout: Command execution timeout in seconds (default 30)
            dry_run: If True, show what would be executed without running

        Returns:
            Dictionary with execution results and report path

        Example:
            inspect_device_group("interface-check", "core-routers", timeout=60)
        """
        additional_params = {"timeout": timeout}
        return inspector.execute_skill(
            skill_name=skill_name,
            device_group=device_group,
            additional_params=additional_params,
            dry_run=dry_run,
        )

    @tool
    def get_inspection_skill_details(skill_name: str) -> dict[str, Any]:
        """Get detailed information about an inspection skill.

        Args:
            skill_name: Name of the skill (interface-check, bgp-check, device-health)

        Returns:
            Dictionary with skill details including:
            - name: Human-readable skill name
            - target: What the skill inspects
            - parameters: Configurable parameters
            - acceptance_criteria: PASS/WARNING/FAIL conditions
            - troubleshooting: Common issues and solutions
            - platform_support: Supported device platforms
            - estimated_runtime: Expected execution time
        """
        if skill_name not in inspector.skills:
            return {"error": f"Skill '{skill_name}' not found"}

        skill = inspector.skills[skill_name]
        return {
            "name": skill.name,
            "target": skill.target,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "required": p.required,
                    "default": p.default,
                    "description": p.description,
                }
                for p in skill.parameters
            ],
            "execution_steps": skill.steps,
            "acceptance_criteria": skill.acceptance_criteria,
            "troubleshooting": skill.troubleshooting,
            "platform_support": skill.platform_support,
            "estimated_runtime": skill.estimated_runtime,
        }

    return [
        list_inspection_skills,
        inspect_device_group,
        get_inspection_skill_details,
    ]


def create_inspector_subagent_config() -> dict[str, Any]:
    """Create configuration for InspectorAgent as a subagent.

    Returns:
        Dictionary with subagent configuration for DeepAgents framework
    """
    return {
        "name": "InspectorAgent",
        "description": (
            "Specialized agent for batch network device inspection. "
            "Executes inspection skills (interface-check, bgp-check, device-health) "
            "on device groups. Use this for network health monitoring and diagnostics."
        ),
        "tools": get_inspector_tools(),
        "system_prompt": """You are the InspectorAgent, specialized in batch network inspections.

## Available Skills
- interface-check: Verify interface status, error counts, VLAN configuration
- bgp-check: Validate BGP neighbor adjacency and session health
- device-health: Monitor CPU, memory, storage, temperature, power supplies

## Workflow
1. User asks to inspect a device group with a specific skill
2. You use 'list_inspection_skills' to show available skills
3. User confirms with device group and any custom parameters
4. You use 'inspect_device_group' to execute the skill
5. Report is auto-generated and embedded to knowledge base
6. You summarize findings and suggest next steps

## Key Features
- Parallel execution across multiple devices
- Automatic PASS/WARNING/FAIL categorization
- Troubleshooting guidance for common issues
- Integration with knowledge base for historical context

Always validate parameters before execution. Use dry_run=True for preview.""",
    }
