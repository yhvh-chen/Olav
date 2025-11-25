"""OpenSearch memory and vector store wrapper."""

import logging
from datetime import UTC
from typing import Any

from opensearchpy import OpenSearch

from olav.core.settings import settings as env_settings

logger = logging.getLogger(__name__)


class OpenSearchMemory:
    """Wrapper for OpenSearch operations - vector search and audit logging."""

    def __init__(self, url: str | None = None) -> None:
        """Initialize OpenSearch client.

        Args:
            url: OpenSearch URL (defaults to env_settings.opensearch_url)
        """
        self.url = url or env_settings.opensearch_url
        self.client = OpenSearch(
            hosts=[self.url],
            http_compress=True,
            use_ssl=False,
            verify_certs=False,
        )

    async def search_schema(
        self,
        index: str,
        query: dict[str, Any],
        size: int = 10,
    ) -> list[dict[str, Any]]:
        """Search schema index with vector or keyword query.

        Args:
            index: Index name (openconfig-schema, suzieq-schema)
            query: OpenSearch query DSL
            size: Max results to return

        Returns:
            List of matching documents
        """
        try:
            response = self.client.search(
                index=index,
                body={"query": query, "size": size},
            )
            return [hit["_source"] for hit in response["hits"]["hits"]]
        except Exception as e:
            logger.error(f"Schema search failed for {index}: {e}")
            return []

    async def log_execution(
        self,
        action: str,
        command: str,
        result: dict[str, Any],
        user: str,
    ) -> None:
        """Log execution to audit index.

        Args:
            action: Action type (query/configure/approve)
            command: Command or query executed
            result: Execution result
            user: User who triggered action
        """
        doc = {
            "action": action,
            "command": command,
            "result": result,
            "user": user,
            "timestamp": "now",
        }

        try:
            self.client.index(
                index="olav-audit",
                body=doc,
            )
            logger.debug(f"Logged {action} by {user}")
        except Exception as e:
            logger.error(f"Failed to log execution: {e}")

    async def store_episodic_memory(
        self,
        intent: str,
        xpath: str,
        success: bool,
        context: dict[str, Any],
    ) -> None:
        """Store successful intent→XPath mapping for learning.

        Args:
            intent: User intent (natural language)
            xpath: OpenConfig XPath used
            success: Whether operation succeeded
            context: Additional context (device, values, etc.)
        """
        from datetime import datetime

        doc = {
            "intent": intent,
            "xpath": xpath,
            "success": success,
            **context,  # Flatten context fields into document
            "timestamp": datetime.now(UTC).isoformat(),
        }

        try:
            self.client.index(
                index="olav-episodic-memory",
                body=doc,
            )
            logger.info(f"Stored episodic memory: {intent} → {xpath}")
        except Exception as e:
            logger.error(f"Failed to store episodic memory: {e}")
