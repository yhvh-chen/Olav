"""Learning Tools - Expose learning capabilities to OLAV agent.

This module wraps the learning functions in LangChain BaseTool wrappers
so they can be used by the agent.
"""

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from olav.core.learning import (
    save_solution,
    suggest_solution_filename,
    update_aliases,
)


class SaveSolutionInput(BaseModel):
    """Input schema for save_solution tool."""

    title: str = Field(description="Case title (filename-safe, e.g., 'crc-errors-r1')")
    problem: str = Field(description="Problem description")
    process: list[str] = Field(description="List of troubleshooting steps taken")
    root_cause: str = Field(description="Root cause analysis")
    solution: str = Field(description="Solution implemented")
    commands: list[str] = Field(description="Key commands used during troubleshooting")
    tags: list[str] = Field(
        description="Tags for indexing (with # prefix, e.g., '#物理层', '#CRC')"
    )


class SaveSolutionTool(BaseTool):
    """Save a successful troubleshooting case to the knowledge base.

    This tool enables the agent to learn from past successes and build a
    solutions library over time. Cases are saved to .olav/knowledge/solutions/.
    """

    name: str = "save_solution"
    description: str = """Save a successful troubleshooting case to the knowledge base.

    Use this tool AFTER successfully resolving a problem. The case will be saved
    to .olav/knowledge/solutions/ as a markdown file for future reference.

    Important: Only save REAL, VERIFIED solutions. Do not save hypothetical cases.
    """
    args_schema: type[BaseModel] = SaveSolutionInput

    def _run(
        self,
        title: str,
        problem: str,
        process: list[str],
        root_cause: str,
        solution: str,
        commands: list[str],
        tags: list[str],
    ) -> str:
        """Execute the tool."""
        try:
            filepath = save_solution(
                title=title,
                problem=problem,
                process=process,
                root_cause=root_cause,
                solution=solution,
                commands=commands,
                tags=tags,
            )
            return f"✅ Solution case saved to: {filepath}"
        except Exception as e:
            return f"❌ Failed to save solution: {e}"


class UpdateAliasesInput(BaseModel):
    """Input schema for update_aliases tool."""

    alias: str = Field(description="The alias (e.g., '核心路由器')")
    actual_value: str = Field(description="What it maps to (e.g., 'R1, R2, R3, R4')")
    alias_type: str = Field(description="Type of alias: device, interface, vlan, etc.")
    platform: str = Field(
        default="unknown", description="Platform if applicable (e.g., 'cisco_ios')"
    )
    notes: str = Field(default="", description="Additional notes about this alias")


class UpdateAliasesTool(BaseTool):
    """Update the aliases knowledge base with a new alias.

    This tool enables the agent to learn device naming conventions and
    aliases used by the network team.
    """

    name: str = "update_aliases"
    description: str = """Update the aliases knowledge base with a new alias.

    Use this tool when the user clarifies what a specific term means.
    For example:
    - User: "核心路由器是R1和R2"
    - You should: update_aliases(alias="核心路由器", actual_value="R1, R2", alias_type="device")

    The alias is saved to .olav/knowledge/aliases.md.
    """
    args_schema: type[BaseModel] = UpdateAliasesInput

    def _run(
        self,
        alias: str,
        actual_value: str,
        alias_type: str,
        platform: str = "unknown",
        notes: str = "",
    ) -> str:
        """Execute the tool."""
        try:
            success = update_aliases(
                alias=alias,
                actual_value=actual_value,
                alias_type=alias_type,
                platform=platform,
                notes=notes,
            )
            if success:
                return f"✅ Alias '{alias}' -> '{actual_value}' saved to knowledge base"
            else:
                return f"❌ Failed to update alias '{alias}'"
        except Exception as e:
            return f"❌ Error updating alias: {e}"


class SuggestSolutionFilenameInput(BaseModel):
    """Input schema for suggest_solution_filename tool."""

    problem_type: str = Field(description="Type of problem (e.g., 'CRC', 'BGP', 'OSPF')")
    device: str = Field(default="", description="Device name (optional)")
    symptom: str = Field(default="", description="Symptom description (optional)")


class SuggestSolutionFilenameTool(BaseTool):
    """Suggest a filename for a solution case.

    This helper tool generates consistent, searchable filenames for solution cases.
    """

    name: str = "suggest_solution_filename"
    description: str = """Suggest a filename for a solution case.

    Use this tool before save_solution to generate a consistent filename.
    The filename will be lowercase, hyphenated, and descriptive.

    Example: suggest_solution_filename(problem_type="CRC", device="R1", symptom="optical power")
    Returns: 'crc-r1-optical-power'
    """
    args_schema: type[BaseModel] = SuggestSolutionFilenameInput

    def _run(
        self,
        problem_type: str,
        device: str = "",
        symptom: str = "",
    ) -> str:
        """Execute the tool."""
        filename = suggest_solution_filename(
            problem_type=problem_type,
            device=device,
            symptom=symptom,
        )
        return f"Suggested filename: {filename}.md"


# Export tool instances
save_solution_tool = SaveSolutionTool()
update_aliases_tool = UpdateAliasesTool()
suggest_filename_tool = SuggestSolutionFilenameTool()

__all__ = [
    "save_solution_tool",
    "update_aliases_tool",
    "suggest_filename_tool",
]
