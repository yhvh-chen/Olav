"""
NetBox Reconciler - Sync differences back to NetBox.

Applies corrections to NetBox based on DiffEngine results,
with HITL approval for critical changes.

LLM-Driven Architecture:
    - Field comparisons handled by LLMDiffEngine (no manual mapping)
    - Simple transforms applied for known field types
    - Extensible to any NetBox plugin without configuration
"""

import logging
from collections.abc import Callable
from typing import Any, ClassVar

from olav.sync.diff_engine import DiffEngine
from olav.sync.models import (
    DiffResult,
    EntityType,
    ReconcileAction,
    ReconcileResult,
    ReconciliationReport,
)
from olav.tools.netbox_tool import NetBoxAPITool

logger = logging.getLogger(__name__)


class NetBoxReconciler:
    """
    Reconciler for syncing network state to NetBox.

    Supports three modes:
    1. Auto-correct: Safe fields updated automatically
    2. HITL: Critical changes require approval
    3. Report-only: Log differences without changes

    Usage:
        reconciler = NetBoxReconciler(netbox_tool)
        results = await reconciler.reconcile(report)
    """

    # Reverse transforms: SuzieQ value → NetBox value
    REVERSE_TRANSFORMS: ClassVar[dict[str, Callable[[Any], Any]]] = {
        "admin_state_to_bool": lambda v: v.lower() == "up" if isinstance(v, str) else bool(v),
        "normalize_speed_to_kbps": lambda v: v * 1000 if isinstance(v, int) else v,
    }

    def __init__(
        self,
        netbox_tool: NetBoxAPITool | None = None,
        diff_engine: DiffEngine | None = None,
        hitl_callback: Callable[[DiffResult], bool] | None = None,
        dry_run: bool = False,
    ) -> None:
        """
        Initialize NetBoxReconciler.

        Args:
            netbox_tool: NetBox API tool (default: create new)
            diff_engine: Diff engine for field classification
            hitl_callback: Callback for HITL approval (receives diff, returns bool)
            dry_run: If True, don't make actual changes
        """
        self.netbox = netbox_tool or NetBoxAPITool()
        self.diff_engine = diff_engine or DiffEngine(netbox_tool=self.netbox)
        self.hitl_callback = hitl_callback
        self.dry_run = dry_run

        # Stats
        self.stats = {
            "auto_corrected": 0,
            "hitl_approved": 0,
            "hitl_rejected": 0,
            "hitl_pending": 0,
            "report_only": 0,
            "errors": 0,
        }

    def _transform_for_netbox(self, entity_type: str, field_name: str, network_value: Any) -> Any:
        """Transform a network value to NetBox format.

        Uses simple built-in transforms for common field types.
        For complex transforms, the LLM can provide context in diff.reason.

        Args:
            entity_type: Entity type (e.g., "interface", "device")
            field_name: Field name (e.g., "enabled", "mtu")
            network_value: Value from network (SuzieQ)

        Returns:
            Transformed value suitable for NetBox API
        """
        # Extract field from path (e.g., "eth0.mtu" → "mtu")
        field = field_name.split(".")[-1] if "." in field_name else field_name

        # Apply built-in transforms based on field name
        if field == "enabled":
            # SuzieQ adminState ("up"/"down") → NetBox boolean
            if isinstance(network_value, str):
                return network_value.lower() == "up"
            return bool(network_value)

        if field == "speed":
            # SuzieQ speed (bps) → NetBox speed (kbps)
            if isinstance(network_value, int):
                return network_value * 1000
            return network_value

        # Default: return as-is
        return network_value

    async def reconcile(
        self,
        report: ReconciliationReport,
        auto_correct: bool = True,
        require_hitl: bool = True,
    ) -> list[ReconcileResult]:
        """
        Reconcile differences from a report.

        Args:
            report: ReconciliationReport from DiffEngine
            auto_correct: Apply auto-corrections for safe fields
            require_hitl: Require approval for critical fields

        Returns:
            List of ReconcileResult for each diff
        """
        results = []

        for diff in report.diffs:
            result = await self._process_diff(diff, auto_correct, require_hitl)
            results.append(result)

            # Update stats
            self.stats[result.action.value] = self.stats.get(result.action.value, 0) + 1

        return results

    async def _process_diff(
        self,
        diff: DiffResult,
        auto_correct: bool,
        require_hitl: bool,
    ) -> ReconcileResult:
        """Process a single diff."""

        # Handle existence differences (create/delete entities)
        if diff.field == "existence":
            return await self._handle_existence_diff(diff, require_hitl)

        # Check if auto-correctable
        if diff.auto_correctable and auto_correct:
            return await self._auto_correct(diff)

        # Check if HITL required
        if self.diff_engine.requires_hitl(diff):
            if require_hitl:
                return await self._request_hitl(diff)
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.SKIPPED,
                success=True,
                message="HITL required but disabled - skipping",
            )

        # Default: report only
        return ReconcileResult(
            diff=diff,
            action=ReconcileAction.REPORT_ONLY,
            success=True,
            message=f"Difference logged: {diff.field}",
        )

    async def _handle_existence_diff(
        self,
        diff: DiffResult,
        require_hitl: bool,
    ) -> ReconcileResult:
        """
        Handle existence differences (create/delete entities).

        Bidirectional sync: Network is source of truth
        - network_value="present", netbox_value="missing" → Create in NetBox
        - network_value="missing", netbox_value="present" → Delete from NetBox (HITL required)
        """
        network_present = diff.network_value == "present"
        netbox_present = diff.netbox_value != "missing"

        # Case 1: Entity exists in network but missing in NetBox → Create
        if network_present and not netbox_present:
            if require_hitl:
                return ReconcileResult(
                    diff=diff,
                    action=ReconcileAction.HITL_PENDING,
                    success=True,
                    message=f"Create {diff.entity_type.value} '{diff.identifier}' in NetBox requires approval",
                )
            return await self._create_entity(diff)

        # Case 2: Entity exists in NetBox but NOT in network → Delete from NetBox
        # Network is source of truth - stale data in NetBox must be cleaned
        if not network_present and netbox_present:
            if require_hitl:
                return ReconcileResult(
                    diff=diff,
                    action=ReconcileAction.HITL_PENDING,
                    success=True,
                    message=f"Delete stale {diff.entity_type.value} '{diff.identifier or diff.netbox_value}' from NetBox requires approval",
                )
            return await self._delete_entity(diff)

        # Default: just report (shouldn't reach here)
        return ReconcileResult(
            diff=diff,
            action=ReconcileAction.REPORT_ONLY,
            success=True,
            message=f"Entity existence difference logged: {diff.network_value} vs {diff.netbox_value}",
        )

    async def _create_entity(self, diff: DiffResult) -> ReconcileResult:
        """Create an entity in NetBox based on network data."""
        if self.dry_run:
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.AUTO_CORRECTED,
                success=True,
                message=f"[DRY RUN] Would create {diff.entity_type.value} '{diff.identifier}' in NetBox",
            )

        try:
            # Determine endpoint and payload based on entity type
            if diff.entity_type == EntityType.INTERFACE:
                return await self._create_interface(diff)
            if diff.entity_type == EntityType.IP_ADDRESS:
                return await self._create_ip_address(diff)
            if diff.entity_type == EntityType.DEVICE:
                # Device creation is complex, report only for now
                return ReconcileResult(
                    diff=diff,
                    action=ReconcileAction.REPORT_ONLY,
                    success=True,
                    message="Device creation requires manual setup in NetBox",
                )
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.REPORT_ONLY,
                success=True,
                message=f"Entity type {diff.entity_type.value} creation not implemented",
            )

        except Exception as e:
            logger.error(f"Entity creation failed: {e}")
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.ERROR,
                success=False,
                message=f"Creation failed: {e!s}",
            )

    async def _create_interface(self, diff: DiffResult) -> ReconcileResult:
        """Create an interface in NetBox."""
        # First, get the device ID
        device_result = await self.netbox.execute(
            path="/api/dcim/devices/",
            method="GET",
            params={"name": diff.device},
        )

        if device_result.error or not device_result.data:
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.ERROR,
                success=False,
                message=f"Cannot find device {diff.device} in NetBox",
            )

        device_id = device_result.data[0].get("id")

        # Create interface
        interface_data = {
            "device": device_id,
            "name": diff.identifier,
            "type": "other",  # Default type, can be refined
        }

        # Add additional data from diff context
        ctx = diff.additional_context or {}
        if ctx.get("description"):
            interface_data["description"] = ctx["description"]
        if "enabled" in ctx:
            interface_data["enabled"] = ctx["enabled"]
        if ctx.get("mtu"):
            interface_data["mtu"] = ctx["mtu"]

        result = await self.netbox.execute(
            path="/api/dcim/interfaces/",
            method="POST",
            data=interface_data,
        )

        if result.error:
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.ERROR,
                success=False,
                message=f"Interface creation failed: {result.error}",
                netbox_response=result.data,
            )

        logger.info(f"Created interface {diff.identifier} on device {diff.device}")

        return ReconcileResult(
            diff=diff,
            action=ReconcileAction.AUTO_CORRECTED,
            success=True,
            message=f"Created interface '{diff.identifier}' on device {diff.device}",
            netbox_response=result.data,
        )

    async def _create_ip_address(self, diff: DiffResult) -> ReconcileResult:
        """Create an IP address in NetBox."""
        # IP address creation requires knowing the interface to assign to
        # For now, we create it unassigned and report
        ip_data = {
            "address": diff.identifier,
            "status": "active",
        }

        # Try to assign to interface if device info is available
        ctx = diff.additional_context or {}
        if diff.device and ctx.get("interface"):
            interface_name = ctx["interface"]
            # Find the interface
            intf_result = await self.netbox.execute(
                path="/api/dcim/interfaces/",
                method="GET",
                params={"device": diff.device, "name": interface_name},
            )
            if not intf_result.error and intf_result.data:
                ip_data["assigned_object_type"] = "dcim.interface"
                ip_data["assigned_object_id"] = intf_result.data[0].get("id")

        result = await self.netbox.execute(
            path="/api/ipam/ip-addresses/",
            method="POST",
            data=ip_data,
        )

        if result.error:
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.ERROR,
                success=False,
                message=f"IP address creation failed: {result.error}",
                netbox_response=result.data,
            )

        logger.info(f"Created IP address {diff.identifier}")

        return ReconcileResult(
            diff=diff,
            action=ReconcileAction.AUTO_CORRECTED,
            success=True,
            message=f"Created IP address '{diff.identifier}'",
            netbox_response=result.data,
        )

    async def _delete_entity(self, diff: DiffResult) -> ReconcileResult:
        """Delete a stale entity from NetBox (network is source of truth)."""
        if self.dry_run:
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.AUTO_CORRECTED,
                success=True,
                message=f"[DRY RUN] Would delete {diff.entity_type.value} '{diff.identifier or diff.netbox_value}' from NetBox",
            )

        # Need netbox_id and endpoint to delete
        if not diff.netbox_id or not diff.netbox_endpoint:
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.ERROR,
                success=False,
                message=f"Cannot delete: missing NetBox ID or endpoint for {diff.entity_type.value}",
            )

        try:
            result = await self.netbox.execute(
                path=f"{diff.netbox_endpoint}{diff.netbox_id}/",
                method="DELETE",
            )

            if result.error:
                return ReconcileResult(
                    diff=diff,
                    action=ReconcileAction.ERROR,
                    success=False,
                    message=f"NetBox delete failed: {result.error}",
                    netbox_response=result.data,
                )

            entity_name = diff.identifier or diff.netbox_value
            logger.info(
                f"Deleted stale {diff.entity_type.value} '{entity_name}' from NetBox (device: {diff.device})"
            )

            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.AUTO_CORRECTED,
                success=True,
                message=f"Deleted stale {diff.entity_type.value} '{entity_name}' from NetBox",
                netbox_response=result.data,
            )

        except Exception as e:
            logger.error(f"Delete entity failed: {e}")
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.ERROR,
                success=False,
                message=f"Delete failed: {e!s}",
            )

    async def _auto_correct(self, diff: DiffResult) -> ReconcileResult:
        """Apply auto-correction for a diff using schema-aware transforms."""
        if self.dry_run:
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.AUTO_CORRECTED,
                success=True,
                message=f"[DRY RUN] Would update {diff.field} to {diff.network_value}",
            )

        if not diff.netbox_id or not diff.netbox_endpoint:
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.ERROR,
                success=False,
                message="Missing NetBox ID or endpoint for update",
            )

        try:
            # Build update payload with schema-aware transforms
            field_name = diff.field.split(".")[-1]

            # Get entity type from diff
            entity_type = diff.entity_type.value.title().replace("_", "")

            # Transform the network value to NetBox format
            netbox_value = self._transform_for_netbox(entity_type, field_name, diff.network_value)

            update_data = {field_name: netbox_value}

            # Execute PATCH
            result = await self.netbox.execute(
                path=f"{diff.netbox_endpoint}{diff.netbox_id}/",
                method="PATCH",
                data=update_data,
            )

            if result.error:
                return ReconcileResult(
                    diff=diff,
                    action=ReconcileAction.ERROR,
                    success=False,
                    message=f"NetBox update failed: {result.error}",
                    netbox_response=result.data,
                )

            logger.info(
                f"Auto-corrected {diff.device}/{diff.field}: {diff.netbox_value} → {diff.network_value}"
            )

            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.AUTO_CORRECTED,
                success=True,
                message=f"Updated {diff.field} from {diff.netbox_value} to {diff.network_value}",
                netbox_response=result.data,
            )

        except Exception as e:
            logger.error(f"Auto-correct failed: {e}")
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.ERROR,
                success=False,
                message=f"Exception: {e!s}",
            )

    async def _request_hitl(self, diff: DiffResult) -> ReconcileResult:
        """Request HITL approval for a diff."""
        if not self.hitl_callback:
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.HITL_PENDING,
                success=True,
                message="HITL approval required - no callback configured",
            )

        try:
            approved = self.hitl_callback(diff)

            if approved:
                # Apply the change
                if self.dry_run:
                    return ReconcileResult(
                        diff=diff,
                        action=ReconcileAction.HITL_APPROVED,
                        success=True,
                        message=f"[DRY RUN] HITL approved - would update {diff.field}",
                    )

                # Actually apply the change
                return await self._apply_hitl_approved(diff)
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.HITL_REJECTED,
                success=True,
                message="Change rejected by operator",
            )

        except Exception as e:
            logger.error(f"HITL callback failed: {e}")
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.ERROR,
                success=False,
                message=f"HITL callback exception: {e!s}",
            )

    async def _apply_hitl_approved(self, diff: DiffResult) -> ReconcileResult:
        """Apply a HITL-approved change."""
        if not diff.netbox_id or not diff.netbox_endpoint:
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.ERROR,
                success=False,
                message="Missing NetBox ID or endpoint for HITL update",
            )

        try:
            field_name = diff.field.split(".")[-1]
            update_data = {field_name: diff.network_value}

            result = await self.netbox.execute(
                path=f"{diff.netbox_endpoint}{diff.netbox_id}/",
                method="PATCH",
                data=update_data,
            )

            if result.error:
                return ReconcileResult(
                    diff=diff,
                    action=ReconcileAction.ERROR,
                    success=False,
                    message=f"HITL update failed: {result.error}",
                    netbox_response=result.data,
                )

            logger.info(f"HITL approved and applied {diff.device}/{diff.field}")

            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.HITL_APPROVED,
                success=True,
                message=f"HITL approved - updated {diff.field}",
                netbox_response=result.data,
            )

        except Exception as e:
            return ReconcileResult(
                diff=diff,
                action=ReconcileAction.ERROR,
                success=False,
                message=f"HITL apply exception: {e!s}",
            )

    def get_stats(self) -> dict[str, int]:
        """Get reconciliation statistics."""
        return self.stats.copy()

    def reset_stats(self) -> None:
        """Reset statistics counters."""
        self.stats = {
            "auto_corrected": 0,
            "hitl_approved": 0,
            "hitl_rejected": 0,
            "hitl_pending": 0,
            "report_only": 0,
            "errors": 0,
        }


async def run_reconciliation(
    devices: list[str],
    dry_run: bool = True,
    auto_correct: bool = True,
) -> tuple[ReconciliationReport, list[ReconcileResult]]:
    """
    Convenience function to run full reconciliation.

    Args:
        devices: List of device hostnames
        dry_run: If True, don't make actual changes
        auto_correct: Apply auto-corrections

    Returns:
        Tuple of (ReconciliationReport, list of ReconcileResults)
    """
    netbox = NetBoxAPITool()
    engine = DiffEngine(netbox_tool=netbox)
    reconciler = NetBoxReconciler(
        netbox_tool=netbox,
        diff_engine=engine,
        dry_run=dry_run,
    )

    # Generate diff report
    report = await engine.compare_all(devices)

    # Apply reconciliation
    results = await reconciler.reconcile(
        report,
        auto_correct=auto_correct,
        require_hitl=True,
    )

    return report, results
