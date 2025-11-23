"""NTC Templates Schema ETL - 索引网络设备命令模板到 OpenSearch."""

import logging
import os
from pathlib import Path
from typing import Any

from opensearchpy import AsyncOpenSearch, helpers

logger = logging.getLogger(__name__)


class NTCSchemaETL:
    """Extract NTC Templates metadata and load to OpenSearch for Schema-Aware CLI."""

    def __init__(self, opensearch_url: str | None = None):
        """Initialize ETL.

        Args:
            opensearch_url: OpenSearch URL (defaults to env var)
        """
        self.opensearch_url = opensearch_url or os.getenv(
            "OPENSEARCH_URL", "http://localhost:9200"
        )
        self.index_name = "ntc-templates-schema"
        self.client: AsyncOpenSearch | None = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.client = AsyncOpenSearch(
            hosts=[self.opensearch_url],
            http_auth=None,  # Add auth if needed
            use_ssl=False,
            verify_certs=False,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.close()

    async def create_index(self):
        """Create ntc-templates-schema index with mappings."""
        mapping = {
            "mappings": {
                "properties": {
                    "platform": {"type": "keyword"},  # cisco_ios, arista_eos, etc.
                    "command": {"type": "text", "analyzer": "standard"},
                    "template_name": {"type": "keyword"},
                    "category": {"type": "keyword"},  # interface, bgp, routing, etc.
                    "intent": {"type": "text"},  # "查看接口状态", "查看BGP邻居"
                    "has_textfsm": {"type": "boolean"},
                    "template_path": {"type": "keyword"},
                }
            }
        }

        if await self.client.indices.exists(index=self.index_name):
            logger.info(f"Index {self.index_name} already exists, deleting...")
            await self.client.indices.delete(index=self.index_name)

        await self.client.indices.create(index=self.index_name, body=mapping)
        logger.info(f"Created index: {self.index_name}")

    def _extract_ntc_templates(self) -> list[dict[str, Any]]:
        """Extract NTC Templates metadata from installed package.

        Returns:
            List of template metadata dicts
        """
        templates = []

        try:
            import ntc_templates

            # Get templates directory from package
            templates_dir = Path(ntc_templates.__file__).parent / "templates"

            if not templates_dir.exists():
                logger.warning(f"NTC templates directory not found: {templates_dir}")
                return templates

            # Parse index file to map platform + command → template
            index_file = templates_dir / "index"
            if not index_file.exists():
                logger.warning(f"NTC templates index not found: {index_file}")
                return templates

            with open(index_file, encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    # Format: platform, command, template_filename
                    # Example: cisco_ios, show ip interface brief, cisco_ios_show_ip_interface_brief.textfsm
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) < 3:
                        logger.debug(f"Skipping malformed line {line_num}: {line}")
                        continue

                    platform, command, template_file = parts[0], parts[1], parts[2]

                    # Infer category and intent from command
                    category = self._infer_category(command)
                    intent = self._infer_intent(command)

                    templates.append(
                        {
                            "platform": platform,
                            "command": command,
                            "template_name": template_file,
                            "category": category,
                            "intent": intent,
                            "has_textfsm": True,
                            "template_path": str(templates_dir / template_file),
                        }
                    )

        except ImportError:
            logger.error(
                "ntc-templates not installed. Run: uv add ntc-templates"
            )
            return []

        logger.info(f"Extracted {len(templates)} NTC templates")
        return templates

    def _infer_category(self, command: str) -> str:
        """Infer category from command string.

        Args:
            command: CLI command

        Returns:
            Category label
        """
        cmd_lower = command.lower()

        if "interface" in cmd_lower:
            return "interface"
        elif "bgp" in cmd_lower:
            return "bgp"
        elif "ospf" in cmd_lower:
            return "ospf"
        elif "route" in cmd_lower or "ip route" in cmd_lower:
            return "routing"
        elif "vlan" in cmd_lower:
            return "vlan"
        elif "mac" in cmd_lower or "arp" in cmd_lower:
            return "l2"
        elif "lldp" in cmd_lower or "cdp" in cmd_lower:
            return "discovery"
        elif "version" in cmd_lower or "inventory" in cmd_lower:
            return "system"
        else:
            return "other"

    def _infer_intent(self, command: str) -> str:
        """Infer user intent from command (for semantic search).

        Args:
            command: CLI command

        Returns:
            Intent description in Chinese
        """
        cmd_lower = command.lower()

        # Interface queries
        if "interface" in cmd_lower and "brief" in cmd_lower:
            return "查看接口状态"
        elif "interface" in cmd_lower:
            return "查看接口详情"

        # BGP queries
        elif "bgp" in cmd_lower and "summary" in cmd_lower:
            return "查看BGP邻居状态"
        elif "bgp" in cmd_lower and "neighbor" in cmd_lower:
            return "查看BGP邻居详情"

        # Routing
        elif "ip route" in cmd_lower or "show route" in cmd_lower:
            return "查看路由表"

        # OSPF
        elif "ospf neighbor" in cmd_lower:
            return "查看OSPF邻居"

        # VLAN
        elif "vlan" in cmd_lower and "brief" in cmd_lower:
            return "查看VLAN列表"

        # MAC/ARP
        elif "mac address-table" in cmd_lower or "mac-address-table" in cmd_lower:
            return "查看MAC地址表"
        elif "arp" in cmd_lower:
            return "查看ARP表"

        # Discovery
        elif "lldp neighbor" in cmd_lower:
            return "查看LLDP邻居"
        elif "cdp neighbor" in cmd_lower:
            return "查看CDP邻居"

        # System
        elif "version" in cmd_lower:
            return "查看设备版本"
        elif "inventory" in cmd_lower:
            return "查看硬件信息"

        else:
            return f"执行命令: {command}"

    async def load_templates(self):
        """Extract and bulk load templates to OpenSearch."""
        templates = self._extract_ntc_templates()

        if not templates:
            logger.warning("No templates to load")
            return

        # Bulk index
        actions = [
            {
                "_index": self.index_name,
                "_source": template,
            }
            for template in templates
        ]

        success, failed = await helpers.async_bulk(
            self.client, actions, raise_on_error=False
        )

        logger.info(
            f"Indexed {success} templates to {self.index_name}, {failed} failed"
        )

    async def run(self):
        """Execute full ETL pipeline."""
        logger.info("Starting NTC Templates Schema ETL...")
        await self.create_index()
        await self.load_templates()
        logger.info("NTC Templates Schema ETL completed")


async def async_main():
    """Async entry point."""
    logging.basicConfig(level=logging.INFO)

    async with NTCSchemaETL() as etl:
        await etl.run()


def main():
    """CLI entry point (sync wrapper for -m invocation)."""
    import asyncio
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
