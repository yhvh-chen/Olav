"""
Tests for NetBox Bidirectional Sync module.

Tests:
- DiffEngine: Compare network state with NetBox
- NetBoxReconciler: Apply corrections
- Rules: Auto-correct and HITL rules
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from olav.sync.models import (
    DiffResult,
    DiffSeverity,
    DiffSource,
    EntityType,
    ReconciliationReport,
    ReconcileAction,
    ReconcileResult,
)
from olav.sync.diff_engine import DiffEngine
from olav.sync.reconciler import NetBoxReconciler
from olav.sync.rules.auto_correct import is_safe_auto_correct, transform_value_for_netbox
from olav.sync.rules.hitl_required import requires_hitl_approval, get_hitl_prompt


class TestModels:
    """Test data models."""
    
    def test_diff_result_creation(self):
        """Test DiffResult creation and serialization."""
        diff = DiffResult(
            entity_type=EntityType.INTERFACE,
            device="R1",
            field="Gi0/1.mtu",
            network_value=1500,
            netbox_value=9000,
            severity=DiffSeverity.INFO,
            source=DiffSource.SUZIEQ,
            auto_correctable=True,
            netbox_id=123,
            netbox_endpoint="/api/dcim/interfaces/",
        )
        
        assert diff.entity_type == EntityType.INTERFACE
        assert diff.device == "R1"
        assert diff.network_value == 1500
        assert diff.auto_correctable is True
        
        # Test serialization
        data = diff.to_dict()
        assert data["entity_type"] == "interface"
        assert data["netbox_id"] == 123
        
        # Test deserialization
        restored = DiffResult.from_dict(data)
        assert restored.entity_type == EntityType.INTERFACE
        assert restored.network_value == 1500
    
    def test_reconciliation_report(self):
        """Test ReconciliationReport aggregation."""
        report = ReconciliationReport(device_scope=["R1", "R2"])
        
        # Add matches
        report.add_match()
        report.add_match()
        
        # Add diffs
        diff1 = DiffResult(
            entity_type=EntityType.INTERFACE,
            device="R1",
            field="mtu",
            network_value=1500,
            netbox_value=9000,
            severity=DiffSeverity.INFO,
            source=DiffSource.SUZIEQ,
        )
        diff2 = DiffResult(
            entity_type=EntityType.IP_ADDRESS,
            device="R2",
            field="existence",
            network_value="10.1.1.1",
            netbox_value="missing",
            severity=DiffSeverity.WARNING,
            source=DiffSource.SUZIEQ,
        )
        
        report.add_diff(diff1)
        report.add_diff(diff2)
        
        assert report.matched == 2
        assert report.mismatched == 2
        assert report.summary_by_type["interface"] == 1
        assert report.summary_by_type["ip_address"] == 1
        assert report.summary_by_severity["info"] == 1
        assert report.summary_by_severity["warning"] == 1
    
    def test_report_to_markdown(self):
        """Test markdown report generation."""
        report = ReconciliationReport(device_scope=["R1"])
        report.add_match()
        report.add_diff(DiffResult(
            entity_type=EntityType.INTERFACE,
            device="R1",
            field="mtu",
            network_value=1500,
            netbox_value=9000,
            severity=DiffSeverity.INFO,
            source=DiffSource.SUZIEQ,
            auto_correctable=True,
        ))
        
        md = report.to_markdown()
        
        assert "# NetBox Sync Report" in md
        assert "R1" in md
        assert "1500" in md
        assert "9000" in md
        assert "✅" in md  # auto_correctable


class TestDiffEngine:
    """Test DiffEngine comparison logic."""
    
    @pytest.fixture
    def mock_netbox(self):
        """Create mock NetBox tool."""
        netbox = MagicMock()
        netbox.execute = AsyncMock()
        return netbox
    
    @pytest.fixture
    def engine(self, mock_netbox):
        """Create DiffEngine with mocked NetBox."""
        return DiffEngine(netbox_tool=mock_netbox)
    
    def test_parse_suzieq_interfaces(self, engine):
        """Test SuzieQ interface parsing."""
        result = {
            "data": [
                {
                    "hostname": "R1",
                    "ifname": "Gi0/1",
                    "state": "up",
                    "adminState": "up",
                    "mtu": 1500,
                    "description": "Uplink",
                },
                {
                    "hostname": "R1",
                    "ifname": "Gi0/2",
                    "state": "down",
                    "adminState": "down",
                    "mtu": 9000,
                },
            ]
        }
        
        interfaces = engine._parse_suzieq_interfaces(result, "R1")
        
        assert len(interfaces) == 2
        assert interfaces["Gi0/1"]["state"] == "up"
        assert interfaces["Gi0/1"]["mtu"] == 1500
        assert interfaces["Gi0/2"]["adminState"] == "down"
    
    def test_parse_netbox_interfaces(self, engine):
        """Test NetBox interface parsing."""
        result = {
            "results": [
                {
                    "id": 1,
                    "name": "Gi0/1",
                    "enabled": True,
                    "mtu": 1500,
                    "description": "Uplink",
                    "type": {"value": "1000base-t"},
                },
            ]
        }
        
        interfaces = engine._parse_netbox_interfaces(result)
        
        assert len(interfaces) == 1
        assert interfaces["Gi0/1"]["id"] == 1
        assert interfaces["Gi0/1"]["enabled"] is True
        assert interfaces["Gi0/1"]["mtu"] == 1500
    
    @pytest.mark.asyncio
    async def test_diff_with_llm_match(self, engine):
        """Test LLM-based interface comparison with matching data."""
        report = ReconciliationReport(device_scope=["R1"])
        
        # Use aligned data - same fields for proper comparison
        suzieq = {
            "Gi0/1": {"adminState": "up", "mtu": 1500}
        }
        netbox = {
            "Gi0/1": {"id": 1, "enabled": True, "mtu": 1500}
        }
        
        await engine._diff_with_llm(
            device="R1",
            entity_type=EntityType.INTERFACE,
            netbox_data=netbox,
            network_data=suzieq,
            report=report,
            endpoint="/api/dcim/interfaces/",
        )
        
        # LLM may report INFO-level diffs for fields that exist in only one source
        # (id exists in NetBox but not network - this is expected)
        # Key assertion: no significant mismatches on comparable fields
        significant_diffs = [d for d in report.diffs if d.field.endswith(".mtu") or d.field.endswith(".enabled")]
        assert len(significant_diffs) == 0, f"Unexpected significant diffs: {significant_diffs}"
    
    @pytest.mark.asyncio
    async def test_diff_with_llm_mtu_mismatch(self, engine):
        """Test LLM-based interface comparison with MTU mismatch."""
        report = ReconciliationReport(device_scope=["R1"])
        
        suzieq = {
            "Gi0/1": {"state": "up", "adminState": "up", "mtu": 1500}
        }
        netbox = {
            "Gi0/1": {"id": 1, "enabled": True, "mtu": 9000}
        }
        
        await engine._diff_with_llm(
            device="R1",
            entity_type=EntityType.INTERFACE,
            netbox_data=netbox,
            network_data=suzieq,
            report=report,
            endpoint="/api/dcim/interfaces/",
        )
        
        # LLM should detect MTU mismatch
        mtu_diffs = [d for d in report.diffs if "mtu" in d.field.lower()]
        assert len(mtu_diffs) >= 1
        mtu_diff = mtu_diffs[0]
        assert mtu_diff.network_value == 1500 or str(mtu_diff.network_value) == "1500"
        assert mtu_diff.netbox_value == 9000 or str(mtu_diff.netbox_value) == "9000"
    
    @pytest.mark.asyncio
    async def test_diff_with_llm_missing_in_netbox(self, engine):
        """Test LLM-based detection of interface in network but not NetBox."""
        report = ReconciliationReport(device_scope=["R1"])
        
        suzieq = {
            "Gi0/1": {"state": "up", "adminState": "up", "mtu": 1500}
        }
        netbox = {}
        
        await engine._diff_with_llm(
            device="R1",
            entity_type=EntityType.INTERFACE,
            netbox_data=netbox,
            network_data=suzieq,
            report=report,
            endpoint="/api/dcim/interfaces/",
        )
        
        # LLM should detect missing entity
        assert report.missing_in_netbox == 1
        existence_diffs = [d for d in report.diffs if "existence" in d.field]
        assert len(existence_diffs) >= 1 or report.missing_in_netbox >= 1
    
    def test_normalize_ip(self, engine):
        """Test IP address normalization."""
        assert engine._normalize_ip("10.1.1.1/32") == "10.1.1.1"
        assert engine._normalize_ip("10.1.1.0/24") == "10.1.1.0/24"
        assert engine._normalize_ip("  10.1.1.1  ") == "10.1.1.1"
    
    def test_is_auto_correctable(self, engine):
        """Test auto-correct field classification."""
        mtu_diff = DiffResult(
            entity_type=EntityType.INTERFACE,
            device="R1",
            field="Gi0/1.mtu",
            network_value=1500,
            netbox_value=9000,
            severity=DiffSeverity.INFO,
            source=DiffSource.SUZIEQ,
        )
        assert engine.is_auto_correctable(mtu_diff) is True
        
        enabled_diff = DiffResult(
            entity_type=EntityType.INTERFACE,
            device="R1",
            field="Gi0/1.enabled",
            network_value=True,
            netbox_value=False,
            severity=DiffSeverity.WARNING,
            source=DiffSource.SUZIEQ,
        )
        assert engine.is_auto_correctable(enabled_diff) is False
    
    def test_requires_hitl(self, engine):
        """Test HITL requirement classification."""
        enabled_diff = DiffResult(
            entity_type=EntityType.INTERFACE,
            device="R1",
            field="Gi0/1.enabled",
            network_value=True,
            netbox_value=False,
            severity=DiffSeverity.WARNING,
            source=DiffSource.SUZIEQ,
        )
        assert engine.requires_hitl(enabled_diff) is True
        
        existence_diff = DiffResult(
            entity_type=EntityType.IP_ADDRESS,
            device="R1",
            field="existence",
            network_value="10.1.1.1",
            netbox_value="missing",
            severity=DiffSeverity.WARNING,
            source=DiffSource.SUZIEQ,
        )
        assert engine.requires_hitl(existence_diff) is True


class TestNetBoxReconciler:
    """Test NetBoxReconciler."""
    
    @pytest.fixture
    def mock_netbox(self):
        """Create mock NetBox tool."""
        netbox = MagicMock()
        netbox.execute = AsyncMock()
        return netbox
    
    @pytest.fixture
    def reconciler(self, mock_netbox):
        """Create reconciler with mocks."""
        return NetBoxReconciler(
            netbox_tool=mock_netbox,
            dry_run=True,
        )
    
    @pytest.mark.asyncio
    async def test_auto_correct_dry_run(self, reconciler):
        """Test auto-correction in dry run mode."""
        diff = DiffResult(
            entity_type=EntityType.INTERFACE,
            device="R1",
            field="Gi0/1.mtu",
            network_value=1500,
            netbox_value=9000,
            severity=DiffSeverity.INFO,
            source=DiffSource.SUZIEQ,
            auto_correctable=True,
            netbox_id=123,
            netbox_endpoint="/api/dcim/interfaces/",
        )
        
        result = await reconciler._auto_correct(diff)
        
        assert result.action == ReconcileAction.AUTO_CORRECTED
        assert result.success is True
        assert "[DRY RUN]" in result.message
    
    @pytest.mark.asyncio
    async def test_process_existence_diff(self, reconciler):
        """Test existence diffs are report-only."""
        diff = DiffResult(
            entity_type=EntityType.INTERFACE,
            device="R1",
            field="existence",
            network_value="Gi0/1",
            netbox_value="missing",
            severity=DiffSeverity.WARNING,
            source=DiffSource.SUZIEQ,
        )
        
        result = await reconciler._process_diff(diff, auto_correct=True, require_hitl=True)
        
        assert result.action == ReconcileAction.REPORT_ONLY
    
    @pytest.mark.asyncio
    async def test_reconcile_report(self, reconciler):
        """Test full report reconciliation."""
        report = ReconciliationReport(device_scope=["R1"])
        report.add_diff(DiffResult(
            entity_type=EntityType.INTERFACE,
            device="R1",
            field="Gi0/1.mtu",
            network_value=1500,
            netbox_value=9000,
            severity=DiffSeverity.INFO,
            source=DiffSource.SUZIEQ,
            auto_correctable=True,
            netbox_id=123,
            netbox_endpoint="/api/dcim/interfaces/",
        ))
        report.add_diff(DiffResult(
            entity_type=EntityType.INTERFACE,
            device="R1",
            field="existence",
            network_value="Gi0/2",
            netbox_value="missing",
            severity=DiffSeverity.WARNING,
            source=DiffSource.SUZIEQ,
        ))
        
        results = await reconciler.reconcile(report)
        
        assert len(results) == 2
        assert results[0].action == ReconcileAction.AUTO_CORRECTED
        assert results[1].action == ReconcileAction.REPORT_ONLY
    
    def test_stats_tracking(self, reconciler):
        """Test statistics tracking."""
        reconciler.stats["auto_corrected"] = 5
        reconciler.stats["hitl_pending"] = 2
        
        stats = reconciler.get_stats()
        assert stats["auto_corrected"] == 5
        assert stats["hitl_pending"] == 2
        
        reconciler.reset_stats()
        assert reconciler.stats["auto_corrected"] == 0


class TestRules:
    """Test auto-correct and HITL rules."""
    
    def test_is_safe_auto_correct_mtu(self):
        """Test MTU is safe to auto-correct."""
        diff = DiffResult(
            entity_type=EntityType.INTERFACE,
            device="R1",
            field="Gi0/1.mtu",
            network_value=1500,
            netbox_value=9000,
            severity=DiffSeverity.INFO,
            source=DiffSource.SUZIEQ,
        )
        assert is_safe_auto_correct(diff) is True
    
    def test_is_safe_auto_correct_enabled(self):
        """Test enabled is NOT safe to auto-correct."""
        diff = DiffResult(
            entity_type=EntityType.INTERFACE,
            device="R1",
            field="Gi0/1.enabled",
            network_value=True,
            netbox_value=False,
            severity=DiffSeverity.WARNING,
            source=DiffSource.SUZIEQ,
        )
        assert is_safe_auto_correct(diff) is False
    
    def test_transform_value_for_netbox(self):
        """Test value transformation for NetBox API."""
        diff = DiffResult(
            entity_type=EntityType.INTERFACE,
            device="R1",
            field="description",
            network_value="New Description",
            netbox_value="Old Description",
            severity=DiffSeverity.INFO,
            source=DiffSource.SUZIEQ,
        )
        
        result = transform_value_for_netbox(diff)
        assert result == "New Description"
    
    def test_requires_hitl_critical_severity(self):
        """Test critical severity requires HITL."""
        diff = DiffResult(
            entity_type=EntityType.INTERFACE,
            device="R1",
            field="some_field",
            network_value="value",
            netbox_value="other",
            severity=DiffSeverity.CRITICAL,
            source=DiffSource.SUZIEQ,
        )
        assert requires_hitl_approval(diff) is True
    
    def test_requires_hitl_existence(self):
        """Test existence changes require HITL."""
        diff = DiffResult(
            entity_type=EntityType.IP_ADDRESS,
            device="R1",
            field="existence",
            network_value="10.1.1.1",
            netbox_value="missing",
            severity=DiffSeverity.WARNING,
            source=DiffSource.SUZIEQ,
        )
        assert requires_hitl_approval(diff) is True
    
    def test_get_hitl_prompt(self):
        """Test HITL prompt generation."""
        diff = DiffResult(
            entity_type=EntityType.INTERFACE,
            device="R1",
            field="Gi0/1.enabled",
            network_value=False,
            netbox_value=True,
            severity=DiffSeverity.WARNING,
            source=DiffSource.SUZIEQ,
        )
        
        prompt = get_hitl_prompt(diff)
        
        assert "HITL Approval Required" in prompt
        assert "R1" in prompt
        assert "interface" in prompt
        assert "Gi0/1.enabled" in prompt
        assert "⚠️" in prompt


# Integration test with mocked data
class TestIntegration:
    """Integration tests for sync workflow."""
    
    @pytest.mark.asyncio
    async def test_full_sync_workflow_dry_run(self):
        """Test complete sync workflow in dry run mode."""
        # Mock NetBox responses
        with patch("olav.sync.diff_engine.NetBoxAPITool") as MockNetBox:
            mock_netbox = MagicMock()
            mock_netbox.execute = AsyncMock()
            MockNetBox.return_value = mock_netbox
            
            # Mock device query
            mock_netbox.execute.return_value = MagicMock(
                error=None,
                data={"results": [{"id": 1, "name": "R1", "serial": "ABC123"}]}
            )
            
            with patch("olav.sync.diff_engine.suzieq_query") as mock_sq:
                mock_sq.ainvoke = AsyncMock(return_value={
                    "data": [{"hostname": "R1", "model": "ISR4451", "version": "16.12.4"}]
                })
                
                # Run sync
                from olav.sync.reconciler import run_reconciliation
                
                report, results = await run_reconciliation(
                    devices=["R1"],
                    dry_run=True,
                    auto_correct=True,
                )
                
                assert report.device_scope == ["R1"]
                # Results depend on mock data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
