"""
NetBox Bidirectional Sync Module.

This module provides:
- LLMDiffEngine: LLM-driven comparison (recommended, zero maintenance)
- DiffEngine: Collect and compare network data with NetBox
- NetBoxReconciler: Sync differences back to NetBox with HITL approval

Architecture:
    Network Data (SuzieQ/CLI) + NetBox Data → LLM Comparison → Reconciliation → NetBox

LLM-Driven Approach:
    - Zero mapping maintenance
    - Automatic adaptation to new NetBox plugins
    - Understands semantic equivalence (enabled=True ↔ adminState="up")
    - Handles interface name variations automatically

Usage:
    from olav.sync import LLMDiffEngine, DiffEngine, NetBoxReconciler

    # LLM-driven comparison (recommended)
    llm_engine = LLMDiffEngine()
    diffs = await llm_engine.compare_entities(
        entity_type="interface",
        device="R1",
        netbox_data=netbox_interfaces,
        network_data=suzieq_interfaces,
    )

    # Full workflow
    diff_engine = DiffEngine()
    report = await diff_engine.compare_all(devices=["R1", "R2"])

    reconciler = NetBoxReconciler()
    results = await reconciler.reconcile(report)
"""

from olav.sync.diff_engine import DiffEngine
from olav.sync.llm_diff import (
    ComparisonResult,
    EntityDiff,
    FieldDiff,
    LLMDiffEngine,
    SimpleDiff,
    comparison_to_diffs,
)
from olav.sync.models import (
    DiffResult,
    DiffSeverity,
    DiffSource,
    EntityType,
    ReconcileAction,
    ReconcileResult,
    ReconciliationReport,
)
from olav.sync.reconciler import NetBoxReconciler

__all__ = [
    # LLM-driven approach (recommended)
    "LLMDiffEngine",
    "ComparisonResult",
    "EntityDiff",
    "FieldDiff",
    "SimpleDiff",
    "comparison_to_diffs",
    # Core components
    "DiffEngine",
    "DiffResult",
    "DiffSeverity",
    "DiffSource",
    "EntityType",
    "NetBoxReconciler",
    "ReconciliationReport",
    "ReconcileAction",
    "ReconcileResult",
]