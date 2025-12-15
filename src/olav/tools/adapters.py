"""
Tool Output Adapters - Normalize vendor-specific formats to ToolOutput.

This module provides adapters to convert various data formats (DataFrame,
XML, parsed CLI text, JSON) into the standardized ToolOutput schema.

Key Adapters:
- SuzieqAdapter: DataFrame → ToolOutput
- CLIAdapter: TextFSM parsed dict → ToolOutput
- NetBoxAdapter: JSON response → ToolOutput
- NetconfAdapter: XML/dict → ToolOutput

Usage:
    from olav.tools.adapters import SuzieqAdapter

    # SuzieQ returns DataFrame
    df = suzieq.bgp.get(hostname="R1")
    output = SuzieqAdapter.adapt(df, device="R1", metadata={"table": "bgp"})

    # Now LLM receives clean JSON
    # output.data = [{"hostname": "R1", "asn": "65001", ...}, ...]
"""

import logging
from typing import Any

from olav.tools.base import ToolOutput

logger = logging.getLogger(__name__)


class SuzieqAdapter:
    """
    Adapter for SuzieQ Parquet query results (pandas DataFrame).

    SuzieQ returns DataFrames which cause LLM hallucination due to
    inconsistent string representations. This adapter normalizes to
    clean JSON dictionaries.
    """

    @staticmethod
    def adapt(
        dataframe: Any,
        device: str = "multi",
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ToolOutput:
        """
        Convert pandas DataFrame to ToolOutput.

        Args:
            dataframe: pandas DataFrame from SuzieQ query
            device: Target device or "multi" for aggregated results
            metadata: Query parameters (table, method, filters)
            error: Error message if query failed

        Returns:
            ToolOutput with normalized data as list of dicts
        """
        try:
            # Handle None or empty DataFrame
            if dataframe is None or (hasattr(dataframe, "empty") and dataframe.empty):
                return ToolOutput(
                    source="suzieq", device=device, data=[], metadata=metadata or {}, error=error
                )

            # Convert DataFrame to list of dicts
            # orient='records' gives [{col1: val1, col2: val2}, ...]
            data = dataframe.to_dict(orient="records")

            # Handle NaN values (convert to None for JSON compatibility)
            import numpy as np

            for record in data:
                for key, value in record.items():
                    if isinstance(value, (np.floating, np.integer)):
                        if np.isnan(value):
                            record[key] = None
                        else:
                            # Convert numpy types to native Python types
                            record[key] = value.item()

            logger.debug(f"SuzieqAdapter: Converted DataFrame with {len(data)} records")

            return ToolOutput(
                source="suzieq", device=device, data=data, metadata=metadata or {}, error=error
            )

        except Exception as e:
            logger.error(f"SuzieqAdapter failed: {e}")
            return ToolOutput(
                source="suzieq",
                device=device,
                data=[],
                metadata=metadata or {},
                error=f"Adapter error: {e}",
            )


class CLIAdapter:
    """
    Adapter for CLI command outputs (TextFSM parsed or raw text).

    CLI tools return either:
    1. TextFSM parsed list of dicts (ideal)
    2. Raw text (needs parsing)
    3. ntc-templates structured output
    """

    @staticmethod
    def adapt(
        cli_output: Any,
        device: str,
        command: str,
        parsed: bool = True,
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ToolOutput:
        """
        Convert CLI output to ToolOutput.

        Args:
            cli_output: Parsed dict list or raw text
            device: Target device hostname
            command: CLI command executed
            parsed: Whether output is already parsed (TextFSM)
            metadata: Additional context (platform, template used)
            error: Error message if command failed

        Returns:
            ToolOutput with normalized data
        """
        try:
            meta = metadata or {}
            meta["command"] = command

            # Case 1: Already parsed (list of dicts)
            if parsed and isinstance(cli_output, list):
                return ToolOutput(
                    source="cli", device=device, data=cli_output, metadata=meta, error=error
                )

            # Case 2: Raw text (wrap in dict)
            if isinstance(cli_output, str):
                logger.warning(
                    f"CLIAdapter: Received raw text for {command}, "
                    f"wrapping in dict (parsing recommended)"
                )
                return ToolOutput(
                    source="cli",
                    device=device,
                    data=[{"raw_output": cli_output}],
                    metadata=meta,
                    error=error,
                )

            # Case 3: Unknown format
            logger.error(f"CLIAdapter: Unknown output type: {type(cli_output)}")
            return ToolOutput(
                source="cli",
                device=device,
                data=[],
                metadata=meta,
                error=f"Unknown output format: {type(cli_output)}",
            )

        except Exception as e:
            logger.error(f"CLIAdapter failed: {e}")
            return ToolOutput(
                source="cli",
                device=device,
                data=[],
                metadata=metadata or {},
                error=f"Adapter error: {e}",
            )


class NetBoxAdapter:
    """
    Adapter for NetBox API responses (JSON dict or list).

    NetBox returns JSON which is already dict-friendly, but we
    standardize the structure and extract relevant fields.
    """

    @staticmethod
    def adapt(
        netbox_response: Any,
        device: str = "netbox",
        endpoint: str = "",
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ToolOutput:
        """
        Convert NetBox API response to ToolOutput.

        Args:
            netbox_response: JSON response from NetBox (dict or list)
            device: "netbox" (not a network device)
            endpoint: API endpoint called (e.g., "/dcim/devices/")
            metadata: Request details (method, filters)
            error: Error message if request failed

        Returns:
            ToolOutput with normalized data
        """
        try:
            meta = metadata or {}
            meta["endpoint"] = endpoint

            # Case 1: List of results
            if isinstance(netbox_response, list):
                return ToolOutput(
                    source="netbox", device=device, data=netbox_response, metadata=meta, error=error
                )

            # Case 2: Single result (dict)
            if isinstance(netbox_response, dict):
                # Check if paginated response
                if "results" in netbox_response:
                    return ToolOutput(
                        source="netbox",
                        device=device,
                        data=netbox_response["results"],
                        metadata={
                            **meta,
                            "count": netbox_response.get("count"),
                            "next": netbox_response.get("next"),
                            "previous": netbox_response.get("previous"),
                        },
                        error=error,
                    )
                # Single object response
                return ToolOutput(
                    source="netbox",
                    device=device,
                    data=[netbox_response],
                    metadata=meta,
                    error=error,
                )

            # Case 3: None or empty
            if netbox_response is None:
                return ToolOutput(
                    source="netbox", device=device, data=[], metadata=meta, error=error
                )

            logger.error(f"NetBoxAdapter: Unknown response type: {type(netbox_response)}")
            return ToolOutput(
                source="netbox",
                device=device,
                data=[],
                metadata=meta,
                error=f"Unknown response format: {type(netbox_response)}",
            )

        except Exception as e:
            logger.error(f"NetBoxAdapter failed: {e}")
            return ToolOutput(
                source="netbox",
                device=device,
                data=[],
                metadata=metadata or {},
                error=f"Adapter error: {e}",
            )


class NetconfAdapter:
    """
    Adapter for NETCONF get-config/get responses (XML or parsed dict).

    NETCONF returns XML which must be parsed into dicts. Libraries like
    ncclient or xmltodict can convert XML to nested dicts.
    """

    @staticmethod
    def adapt(
        netconf_response: Any,
        device: str,
        xpath: str = "",
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ToolOutput:
        """
        Convert NETCONF response to ToolOutput.

        Args:
            netconf_response: Parsed dict from xmltodict or similar
            device: Target device hostname
            xpath: XPath filter used in query
            metadata: Additional context (operation, namespace)
            error: Error message if operation failed

        Returns:
            ToolOutput with normalized data
        """
        try:
            meta = metadata or {}
            meta["xpath"] = xpath

            # Case 0: None response
            # Many NETCONF operations (especially edit-config) may return no payload.
            # Preserve the provided error (if any) rather than overwriting it.
            if netconf_response is None:
                return ToolOutput(
                    source="netconf",
                    device=device,
                    data=[],
                    metadata=meta,
                    error=error,
                )

            # Case 1: Already parsed dict
            if isinstance(netconf_response, dict):
                # Flatten nested structures if needed
                # (implementation depends on data structure)
                return ToolOutput(
                    source="netconf",
                    device=device,
                    data=[netconf_response],
                    metadata=meta,
                    error=error,
                )

            # Case 2: List of dicts
            if isinstance(netconf_response, list):
                return ToolOutput(
                    source="netconf",
                    device=device,
                    data=netconf_response,
                    metadata=meta,
                    error=error,
                )

            # Case 3: Raw XML string (parse it)
            if isinstance(netconf_response, str):
                logger.warning(
                    "NetconfAdapter: Received raw XML, wrapping in dict (parsing recommended)"
                )
                return ToolOutput(
                    source="netconf",
                    device=device,
                    data=[{"raw_xml": netconf_response}],
                    metadata=meta,
                    error=error,
                )

            logger.error(f"NetconfAdapter: Unknown response type: {type(netconf_response)}")
            return ToolOutput(
                source="netconf",
                device=device,
                data=[],
                metadata=meta,
                error=error or f"Unknown response format: {type(netconf_response)}",
            )

        except Exception as e:
            logger.error(f"NetconfAdapter failed: {e}")
            return ToolOutput(
                source="netconf",
                device=device,
                data=[],
                metadata=metadata or {},
                error=f"Adapter error: {e}",
            )


class OpenSearchAdapter:
    """
    Adapter for OpenSearch query results.

    Used for RAG queries (schema index, episodic memory, documents).
    """

    @staticmethod
    def adapt(
        opensearch_hits: list[dict[str, Any]],
        index: str,
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ToolOutput:
        """
        Convert OpenSearch hits to ToolOutput.

        Args:
            opensearch_hits: List of hit dicts from ES response
            index: Index name queried
            metadata: Query details (query DSL, filters)
            error: Error message if query failed

        Returns:
            ToolOutput with normalized data
        """
        try:
            meta = metadata or {}
            meta["index"] = index

            # Extract _source from each hit
            data = [hit.get("_source", hit) for hit in opensearch_hits]

            return ToolOutput(
                source="opensearch", device="opensearch", data=data, metadata=meta, error=error
            )

        except Exception as e:
            logger.error(f"OpenSearchAdapter failed: {e}")
            return ToolOutput(
                source="opensearch",
                device="opensearch",
                data=[],
                metadata=metadata or {},
                error=f"Adapter error: {e}",
            )
