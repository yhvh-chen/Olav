"""OLAV Modes - Three isolated execution modes.

Mode Architecture:
    - Standard Mode: Fast single-step queries (UnifiedClassifier + FastPathExecutor)
    - Expert Mode: Multi-step fault diagnosis (Supervisor + L1-L4 Inspectors)
    - Inspection Mode: YAML-driven batch audits (IntentCompiler + MapReduce)

Each mode is completely isolated with its own entry point.
"""

from enum import Enum


class Mode(str, Enum):
    """Execution mode enumeration."""

    STANDARD = "standard"
    EXPERT = "expert"
    INSPECTION = "inspection"


__all__ = ["Mode"]
