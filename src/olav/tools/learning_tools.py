"""Learning Tools - Expose learning capabilities to OLAV agent.

This module wraps the learning functions in LangChain BaseTool wrappers
so they can be used by the agent.

Simplified version: Only update_aliases for device naming conventions.
Manual solution documentation kept for user control.
"""

from pathlib import Path

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from config.settings import settings
from olav.core.learning import suggest_solution_filename, update_aliases
from olav.tools.knowledge_embedder import KnowledgeEmbedder


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

    The alias is saved to agent_dir/knowledge/aliases.md.
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


class EmbedKnowledgeInput(BaseModel):
    """Input schema for embed_knowledge tool."""

    file_path: str = Field(description="Path to markdown file to embed (relative or absolute)")
    source_type: str = Field(
        default="report",
        description="Type of source: 'report', 'skill', 'solution', or 'knowledge'",
    )
    platform: str = Field(
        default=None,
        description="Optional platform tag (e.g., 'cisco_ios', 'huawei_vrp', 'report')",
    )


class EmbedKnowledgeTool(BaseTool):
    """Embed a markdown file or directory to the knowledge vector database.

    Phase 7: Agentic embedding for reports and skills. This tool enables
    the agent to index new knowledge to the DuckDB vector store.
    """

    name: str = "embed_knowledge"
    description: str = """Embed a markdown file or directory to the knowledge vector database.

    Use this tool to index new reports, skills, or knowledge files to make them
    available for semantic search and agentic retrieval.

    Examples:
    - embed_knowledge(file_path="data/reports/network-analysis-2026-01-10.md", source_type="report")
    - embed_knowledge(file_path=".olav/skills/inspection/", source_type="skill")

    Returns: Summary of indexed chunks and any errors.
    """
    args_schema: type[BaseModel] = EmbedKnowledgeInput

    def _run(
        self,
        file_path: str,
        source_type: str = "report",
        platform: str = None,
    ) -> str:
        """Execute the tool."""
        try:
            embedder = KnowledgeEmbedder()

            path = Path(file_path)

            # Resolve path (handle relative paths)
            if not path.is_absolute():
                if path.exists():
                    pass  # Relative path exists in cwd
                else:
                    # Try relative to agent_dir
                    agent_path = Path(settings.agent_dir) / path
                    if agent_path.exists():
                        path = agent_path

            if not path.exists():
                return f"❌ Error: File or directory not found: {file_path}"

            # Map source_type to source_id
            source_type_map = {
                "skill": 1,
                "knowledge": 2,
                "report": 3,
                "solution": 2,
            }
            source_id = source_type_map.get(source_type, 3)

            # Embed single file or directory
            if path.is_file():
                if not path.suffix.lower() == ".md":
                    return f"❌ Error: Only markdown files (.md) are supported. Got: {path.suffix}"

                count = embedder.embed_file(path, source_id=source_id, platform=platform)
                if count > 0:
                    return f"✅ Embedded {path.name}: {count} chunks indexed"
                else:
                    return f"⚠️ File already indexed or empty: {path.name}"
            else:
                # Embed directory
                stats = embedder.embed_directory(path, source_id=source_id, platform=platform)
                total = stats["indexed"]
                if total > 0:
                    return (
                        f"✅ Embedded directory: {total} chunks indexed, {stats['skipped']} skipped"
                    )
                else:
                    return f"⚠️ No new files to embed in directory: {path}"

        except Exception as e:
            return f"❌ Error embedding knowledge: {e}"


# Export tool instances
update_aliases_tool = UpdateAliasesTool()
suggest_filename_tool = SuggestSolutionFilenameTool()
embed_knowledge_tool = EmbedKnowledgeTool()

__all__ = [
    "update_aliases_tool",
    "suggest_filename_tool",
    "embed_knowledge_tool",
]
