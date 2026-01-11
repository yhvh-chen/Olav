"""Research tool for network troubleshooting - combines local knowledge base and web search."""

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from olav.tools.knowledge_search import search_knowledge


class ResearchProblemInput(BaseModel):
    """Input schema for research tool."""

    query: str = Field(
        description="Problem description or keyword to research. "
        "e.g., 'BGP flapping', 'OSPF convergence issues'"
    )
    platform: str = Field(
        default="all",
        description="Network platform/vendor (cisco, juniper, arista, all)",
    )
    include_web_search: bool = Field(
        default=True,
        description="Whether to include web search results",
    )


class ResearchProblemTool(BaseTool):
    """Comprehensive research tool for network troubleshooting.

    Combines:
    1. Local knowledge base search (vector similarity + BM25)
    2. Web search (fallback if local results insufficient)

    Intelligently decides when to use web search based on:
    - Local search result count and confidence
    - User preference (include_web_search parameter)
    - Settings configuration

    This tool is read-only and does not require approval.
    """

    name: str = "research_problem"
    description: str = (
        "Research a network problem using local knowledge base and web search. "
        "Perfect for troubleshooting unfamiliar issues, finding vendor documentation, "
        "or discovering new solutions. E.g., research_problem('BGP flapping on Cisco IOS-XR')"
    )
    args_schema: type[BaseModel] = ResearchProblemInput

    def _run(
        self,
        query: str,
        platform: str = "all",
        include_web_search: bool = True,
    ) -> str:
        """Execute research workflow.

        Args:
            query: Problem description or keyword
            platform: Network platform/vendor
            include_web_search: Whether to use web search as fallback

        Returns:
            Research findings combining local and web sources
        """
        # Step 1: Search local knowledge base
        local_results = search_knowledge(query, platform, limit=5)

        # Decision logic: when to use web search
        use_web_search = include_web_search and self._should_use_web_search(local_results, query)

        if not use_web_search:
            return local_results if local_results else f"No local knowledge found for: {query}"

        # Step 2: If local results insufficient, try web search
        web_results = self._web_search(query, platform)

        if web_results:
            return self._merge_results(local_results, web_results)

        return (
            local_results
            if local_results
            else f"No information found locally or online for: {query}"
        )

    def _should_use_web_search(self, local_results: str, query: str) -> bool:
        """Determine if web search should be used.

        Heuristics:
        - Empty local results
        - Very short results (< 200 chars)
        - Queries with version/model numbers (likely specific)
        """
        from config.settings import settings

        if not settings.diagnosis.enable_web_search:
            return False

        if not local_results or "No" in local_results[:50]:
            return True

        # Use web search if results are too short (likely incomplete)
        if len(local_results) < 200:
            return True

        # Use web search for specific version queries
        if any(
            keyword in query.lower()
            for keyword in ["version", "ios-xr", "junos", "eos", "bug", "cve"]
        ):
            return True

        return False

    def _web_search(self, query: str, platform: str) -> str | None:
        """Perform web search with timeout and error handling.

        Args:
            query: Search query
            platform: Platform/vendor context

        Returns:
            Search results or None if failed
        """
        try:
            from langchain_community.tools import DuckDuckGoSearchResults

            from config.settings import settings

            # Construct vendor-aware query
            if platform != "all":
                search_query = f"{platform} {query}"
            else:
                search_query = query

            # Use configured max results
            max_results = getattr(settings.diagnosis, "web_search_max_results", 3)

            search = DuckDuckGoSearchResults(max_results=max_results)
            results = search.invoke(search_query)

            if results and "No good" not in results:
                return results

            return None

        except ImportError:
            return None
        except Exception as e:
            # Graceful degradation: log but don't fail
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Web search failed: {str(e)}")
            return None

    def _merge_results(self, local_results: str, web_results: str) -> str:
        """Merge local and web search results intelligently.

        Format: Local results first (higher priority), then web results
        """
        return f"""## Local Knowledge Base
{local_results}

---

## Web Search Results
{web_results}

---

**Note**: Local knowledge base results are prioritized as they reflect your specific
network environment. Web results provide vendor documentation and broader experiences.
"""

    async def _arun(self, *args: tuple, **kwargs: dict) -> str:
        """Async version (falls back to sync)."""
        return self._run(*args, **kwargs)


# Create singleton instance
research_problem_tool = ResearchProblemTool()
