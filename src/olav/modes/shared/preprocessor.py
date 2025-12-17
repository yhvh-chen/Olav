"""
Query Preprocessor - Device Extraction and Intent Classification.

This module provides:
1. Device name extraction from natural language queries
2. Intent classification (diagnostic vs query) for mode routing

Note: Tool classification is now handled by ToolRegistry.keyword_match()
in unified_classifier.py (Tool Self-Declaration pattern).

Design principles:
- Shared extraction logic for Standard and Expert modes
- Separate intent classification (diagnostic vs query)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)


# =============================================================================
# Intent Classification Keywords
# =============================================================================

# Diagnostic keywords → Expert Mode (requires LLM planning)
DIAGNOSTIC_KEYWORDS: frozenset[str] = frozenset({
    # English diagnostic terms
    "why", "diagnose", "analyze", "troubleshoot", "failure", "issue", "problem",
    "root cause", "investigate", "debug", "fault", "unreachable", "packet loss",
    "high latency", "unstable", "down", "disconnected", "error", "abnormal",
})

# Query keywords → Standard Mode
QUERY_KEYWORDS: frozenset[str] = frozenset({
    # English query terms
    "show", "list", "get", "display", "check", "query", "find", "search",
    "retrieve", "view", "lookup", "status", "state", "summary",
})


# =============================================================================
# Device Name Extraction
# =============================================================================

# Common device naming patterns (shared between modes)
DEVICE_PATTERNS: list[re.Pattern[str]] = [
    # Explicit device reference: "device R1", "host spine-1"
    re.compile(r"(?:device|host|router|switch)\s*[:\s]?\s*(?P<device>[A-Za-z][\w\-\.]+)", re.IGNORECASE),
    # Possessive: "R1's"
    re.compile(r"(?P<device>[A-Za-z][\w\-\.]+)\s*(?:'s)\s+(?:BGP|OSPF|interface|route)", re.IGNORECASE),
    # Context: "on R1"
    re.compile(r"(?:on)\s+(?P<device>[A-Za-z][\w\-\.]+)\s*(?:$)", re.IGNORECASE),
    # Direct mention with table context
    re.compile(r"(?:show|get|query)\s+(?P<device>[A-Za-z][\w\-\.]+)\s+(?:BGP|OSPF|interface|route)", re.IGNORECASE),
]


# =============================================================================
# Preprocessor Result
# =============================================================================

@dataclass
class PreprocessResult:
    """Result of query preprocessing."""

    # Intent classification
    intent_type: Literal["diagnostic", "query", "unknown"]

    # Extracted entities (shared between modes)
    devices: list[str] = field(default_factory=list)

    # Original query for reference
    original_query: str = ""

    @property
    def is_diagnostic(self) -> bool:
        """Check if this is a diagnostic query requiring Expert Mode."""
        return self.intent_type == "diagnostic"


class QueryPreprocessor:
    """
    Preprocesses user queries to extract entities and determine intent.

    This is a shared component used by both Standard and Expert modes:
    - Standard Mode: Uses intent to route (query vs diagnostic)
    - Expert Mode: Uses extracted devices as investigation starting points

    Note: Tool selection is now handled by ToolRegistry.keyword_match()
    in unified_classifier.py.

    Usage:
        preprocessor = QueryPreprocessor()
        result = preprocessor.process("query R1 BGP status")

        if result.is_diagnostic:
            # Expert Mode
            devices = result.devices
        else:
            # Standard Mode - tool selection via UnifiedClassifier
            ...
    """

    def __init__(self) -> None:
        """Initialize the preprocessor."""
        self._device_patterns = DEVICE_PATTERNS

    def process(self, query: str) -> PreprocessResult:
        """
        Process a query to extract entities and determine intent.

        Args:
            query: User's natural language query.

        Returns:
            PreprocessResult with intent type and extracted devices.
        """
        # 1. Classify intent (diagnostic vs query)
        intent_type = self._classify_intent(query)

        # 2. Extract device names (shared)
        devices = self._extract_devices(query)

        result = PreprocessResult(
            intent_type=intent_type,
            devices=devices,
            original_query=query,
        )

        logger.debug(f"Preprocessed query: intent={intent_type}, devices={devices}")

        return result

    def _classify_intent(self, query: str) -> Literal["diagnostic", "query", "unknown"]:
        """
        Classify query intent based on keywords.

        Diagnostic queries require multi-step analysis (Expert Mode).
        Query queries are simple data retrieval (Standard Mode).
        """
        query_lower = query.lower()

        # Check diagnostic keywords first (higher priority)
        if any(kw in query_lower for kw in DIAGNOSTIC_KEYWORDS):
            return "diagnostic"

        # Check query keywords
        if any(kw in query_lower for kw in QUERY_KEYWORDS):
            return "query"

        # Default to query for network-related terms
        network_terms = {"bgp", "ospf", "interface", "route", "vlan", "mac", "lldp"}
        if any(term in query_lower for term in network_terms):
            return "query"

        return "unknown"

    def _extract_devices(self, query: str) -> list[str]:
        """
        Extract device names from query using multiple patterns.

        Returns list of unique device names found.
        """
        devices: set[str] = set()

        for pattern in self._device_patterns:
            for match in pattern.finditer(query):
                device = match.group("device")
                if device and self._is_valid_device_name(device):
                    devices.add(device)

        return list(devices)

    def _is_valid_device_name(self, name: str) -> bool:
        """
        Validate that a string looks like a device name.

        Filters out common false positives like keywords.
        """
        # Too short
        if len(name) < 2:
            return False

        # Common false positives
        false_positives = {
            "bgp", "ospf", "vlan", "mac", "lldp", "interface", "route", "show",
            "list", "get", "query", "check", "all", "the", "and", "for",
            "status", "neighbor", "device", "devices",
        }
        if name.lower() in false_positives:
            return False

        return True


# =============================================================================
# Module-level convenience functions
# =============================================================================

# Singleton instance
_preprocessor: QueryPreprocessor | None = None


def get_preprocessor() -> QueryPreprocessor:
    """Get singleton preprocessor instance."""
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = QueryPreprocessor()
    return _preprocessor


def preprocess_query(query: str) -> PreprocessResult:
    """
    Convenience function to preprocess a query.

    Args:
        query: User's natural language query.

    Returns:
        PreprocessResult with intent and devices.
    """
    return get_preprocessor().process(query)
