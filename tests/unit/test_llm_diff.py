"""Tests for LLM-driven diff engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from olav.sync.llm_diff import (
    LLMDiffEngine,
    ComparisonResult,
    EntityDiff,
    FieldDiff,
    comparison_to_diffs,
)
from olav.sync.models import DiffSeverity, EntityType


class TestPydanticModels:
    """Test Pydantic model validation."""

    def test_field_diff_creation(self):
        """Test FieldDiff model."""
        diff = FieldDiff(
            field_name="mtu",
            netbox_value=1500,
            network_value=9000,
            semantic_match=False,
            severity="warning",
            explanation="MTU mismatch",
        )
        assert diff.field_name == "mtu"
        assert diff.severity == "warning"

    def test_entity_diff_creation(self):
        """Test EntityDiff model."""
        entity = EntityDiff(
            entity_type="interface",
            identifier="GigabitEthernet0/0",
            exists_in_netbox=True,
            exists_in_network=True,
            field_diffs=[
                FieldDiff(
                    field_name="description",
                    netbox_value="Uplink",
                    network_value="uplink to core",
                    severity="info",
                    explanation="Description differs",
                )
            ],
            auto_correctable=True,
        )
        assert entity.entity_type == "interface"
        assert len(entity.field_diffs) == 1
        assert entity.auto_correctable

    def test_comparison_result_creation(self):
        """Test ComparisonResult model."""
        result = ComparisonResult(
            device="R1",
            entity_diffs=[],
            summary="No differences found",
            total_entities=10,
            matched=10,
            mismatched=0,
        )
        assert result.device == "R1"
        assert result.matched == 10

    def test_field_diff_defaults(self):
        """Test FieldDiff default values."""
        diff = FieldDiff(
            field_name="test",
            netbox_value="a",
            network_value="b",
            explanation="test",
        )
        assert diff.semantic_match is False
        assert diff.severity == "info"


class TestComparisonToDiffs:
    """Test conversion from ComparisonResult to legacy DiffResult."""

    def test_missing_in_netbox(self):
        """Test conversion of entity missing in NetBox."""
        result = ComparisonResult(
            device="R1",
            entity_diffs=[
                EntityDiff(
                    entity_type="interface",
                    identifier="Loopback0",
                    exists_in_netbox=False,
                    exists_in_network=True,
                )
            ],
            summary="1 interface missing in NetBox",
        )

        diffs = comparison_to_diffs(result)

        assert len(diffs) == 1
        assert diffs[0].entity_type == EntityType.INTERFACE
        assert diffs[0].field == "existence"
        assert diffs[0].network_value == "present"
        assert diffs[0].netbox_value == "missing"
        assert diffs[0].identifier == "Loopback0"

    def test_missing_in_network(self):
        """Test conversion of entity missing in network."""
        result = ComparisonResult(
            device="R1",
            entity_diffs=[
                EntityDiff(
                    entity_type="interface",
                    identifier="Vlan99",
                    exists_in_netbox=True,
                    exists_in_network=False,
                )
            ],
            summary="1 stale interface in NetBox",
        )

        diffs = comparison_to_diffs(result)

        assert len(diffs) == 1
        assert diffs[0].network_value == "missing"
        assert diffs[0].netbox_value == "present"

    def test_field_diff_conversion(self):
        """Test conversion of field differences."""
        result = ComparisonResult(
            device="R1",
            entity_diffs=[
                EntityDiff(
                    entity_type="interface",
                    identifier="Gi0/0",
                    field_diffs=[
                        FieldDiff(
                            field_name="mtu",
                            netbox_value=1500,
                            network_value=9000,
                            severity="warning",
                            explanation="MTU differs",
                        )
                    ],
                    auto_correctable=True,
                )
            ],
            summary="MTU mismatch",
        )

        diffs = comparison_to_diffs(result)

        assert len(diffs) == 1
        assert diffs[0].field == "Gi0/0.mtu"
        assert diffs[0].network_value == 9000
        assert diffs[0].netbox_value == 1500
        assert diffs[0].severity == DiffSeverity.WARNING
        assert diffs[0].auto_correctable is True

    def test_semantic_match_skipped(self):
        """Test that semantic matches are not converted to diffs."""
        result = ComparisonResult(
            device="R1",
            entity_diffs=[
                EntityDiff(
                    entity_type="interface",
                    identifier="Gi0/0",
                    field_diffs=[
                        FieldDiff(
                            field_name="state",
                            netbox_value=True,
                            network_value="up",
                            semantic_match=True,  # Should be skipped
                            severity="info",
                            explanation="Enabled vs up - equivalent",
                        )
                    ],
                )
            ],
            summary="All equivalent",
        )

        diffs = comparison_to_diffs(result)

        assert len(diffs) == 0  # Semantic match should be skipped

    def test_multiple_entities(self):
        """Test conversion with multiple entities."""
        result = ComparisonResult(
            device="R1",
            entity_diffs=[
                EntityDiff(
                    entity_type="interface",
                    identifier="Gi0/0",
                    exists_in_netbox=False,
                    exists_in_network=True,
                ),
                EntityDiff(
                    entity_type="ip_address",
                    identifier="10.1.1.1/24",
                    field_diffs=[
                        FieldDiff(
                            field_name="status",
                            netbox_value="active",
                            network_value="configured",
                            severity="info",
                            explanation="Status format differs",
                        )
                    ],
                ),
            ],
            summary="Multiple differences",
        )

        diffs = comparison_to_diffs(result)

        assert len(diffs) == 2
        assert diffs[0].entity_type == EntityType.INTERFACE
        assert diffs[1].entity_type == EntityType.IP_ADDRESS


class TestLLMDiffEngine:
    """Test LLMDiffEngine class."""

    @pytest.mark.asyncio
    async def test_compare_with_mock_llm(self):
        """Test comparison with mocked LLM."""
        # Create mock model
        mock_result = ComparisonResult(
            device="R1",
            entity_diffs=[
                EntityDiff(
                    entity_type="interface",
                    identifier="Gi0/0",
                    field_diffs=[
                        FieldDiff(
                            field_name="mtu",
                            netbox_value=1500,
                            network_value=9000,
                            severity="warning",
                            explanation="MTU mismatch",
                        )
                    ],
                )
            ],
            summary="1 MTU difference",
            total_entities=5,
            matched=4,
            mismatched=1,
        )

        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = mock_result

        engine = LLMDiffEngine(model=mock_model)

        result = await engine.compare(
            device="R1",
            netbox_data={"interfaces": [{"name": "Gi0/0", "mtu": 1500}]},
            network_data={"interfaces": [{"ifname": "Gi0/0", "mtu": 9000}]},
        )

        assert result.device == "R1"
        assert result.mismatched == 1
        assert len(result.entity_diffs) == 1
        mock_model.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_compare_interfaces_helper(self):
        """Test compare_interfaces convenience method."""
        mock_result = ComparisonResult(
            device="R1",
            entity_diffs=[],
            summary="All match",
        )

        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = mock_result

        engine = LLMDiffEngine(model=mock_model)

        result = await engine.compare_interfaces(
            device="R1",
            netbox_interfaces=[{"name": "Gi0/0"}],
            network_interfaces=[{"ifname": "Gi0/0"}],
        )

        assert result.device == "R1"

    @pytest.mark.asyncio
    async def test_compare_error_handling(self):
        """Test error handling during comparison."""
        mock_model = AsyncMock()
        mock_model.ainvoke.side_effect = Exception("LLM API error")

        engine = LLMDiffEngine(model=mock_model)

        result = await engine.compare(
            device="R1",
            netbox_data={},
            network_data={},
        )

        # Should return empty result with error message
        assert result.device == "R1"
        assert "failed" in result.summary.lower()
        assert len(result.entity_diffs) == 0


class TestValueTransformations:
    """Test value transformation methods in LLMDiffEngine."""

    def test_map_interface_type_loopback(self):
        """Test loopback interface type mapping."""
        engine = LLMDiffEngine()
        assert engine.map_interface_type("loopback") == "virtual"
        assert engine.map_interface_type("Loopback") == "virtual"
        assert engine.map_interface_type(None, "Loopback0") == "virtual"
        assert engine.map_interface_type(None, "lo0") == "virtual"

    def test_map_interface_type_ethernet(self):
        """Test ethernet interface type mapping."""
        engine = LLMDiffEngine()
        assert engine.map_interface_type("ethernet") == "1000base-t"
        assert engine.map_interface_type("gigabit") == "1000base-t"
        assert engine.map_interface_type(None, "GigabitEthernet0/0") == "1000base-t"
        assert engine.map_interface_type(None, "eth0") == "1000base-t"

    def test_map_interface_type_vlan(self):
        """Test VLAN interface type mapping."""
        engine = LLMDiffEngine()
        assert engine.map_interface_type("vlan") == "virtual"
        assert engine.map_interface_type("svi") == "virtual"
        assert engine.map_interface_type(None, "Vlan100") == "virtual"

    def test_map_interface_type_lag(self):
        """Test LAG interface type mapping."""
        engine = LLMDiffEngine()
        assert engine.map_interface_type("lag") == "lag"
        assert engine.map_interface_type("bond") == "lag"
        assert engine.map_interface_type("port-channel") == "lag"

    def test_map_interface_type_unknown(self):
        """Test unknown interface type returns 'other'."""
        engine = LLMDiffEngine()
        assert engine.map_interface_type("unknown") == "other"
        assert engine.map_interface_type(None, "weird0") == "other"
        assert engine.map_interface_type(None, None) == "other"

    def test_normalize_speed_gbps(self):
        """Test speed normalization from Gbps."""
        engine = LLMDiffEngine()
        assert engine.normalize_speed(1) == 1_000_000  # 1 Gbps
        assert engine.normalize_speed(10) == 10_000_000  # 10 Gbps
        assert engine.normalize_speed(100) == 100_000_000  # 100 Gbps

    def test_normalize_speed_mbps(self):
        """Test speed normalization from Mbps."""
        engine = LLMDiffEngine()
        assert engine.normalize_speed(1000) == 1_000_000  # 1000 Mbps
        assert engine.normalize_speed(10000) == 10_000_000  # 10000 Mbps

    def test_normalize_speed_kbps(self):
        """Test speed normalization from kbps (passthrough)."""
        engine = LLMDiffEngine()
        assert engine.normalize_speed(1_000_000) == 1_000_000
        assert engine.normalize_speed(10_000_000) == 10_000_000

    def test_normalize_speed_bps(self):
        """Test speed normalization from bps."""
        engine = LLMDiffEngine()
        assert engine.normalize_speed(1_000_000_000) == 1_000_000  # 1 Gbps in bps

    def test_normalize_speed_invalid(self):
        """Test speed normalization with invalid values."""
        engine = LLMDiffEngine()
        assert engine.normalize_speed(None) is None
        assert engine.normalize_speed(0) is None
        assert engine.normalize_speed(-1) is None
        assert engine.normalize_speed("invalid") is None

    def test_normalize_mac_colon_format(self):
        """Test MAC normalization from colon format."""
        engine = LLMDiffEngine()
        assert engine.normalize_mac("aa:bb:cc:dd:ee:ff") == "AA:BB:CC:DD:EE:FF"
        assert engine.normalize_mac("AA:BB:CC:DD:EE:FF") == "AA:BB:CC:DD:EE:FF"

    def test_normalize_mac_dash_format(self):
        """Test MAC normalization from dash format."""
        engine = LLMDiffEngine()
        assert engine.normalize_mac("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"

    def test_normalize_mac_dot_format(self):
        """Test MAC normalization from Cisco dot format."""
        engine = LLMDiffEngine()
        assert engine.normalize_mac("aabb.ccdd.eeff") == "AA:BB:CC:DD:EE:FF"

    def test_normalize_mac_invalid(self):
        """Test MAC normalization with invalid values."""
        engine = LLMDiffEngine()
        assert engine.normalize_mac(None) is None
        assert engine.normalize_mac("") is None
        assert engine.normalize_mac("invalid") is None
        assert engine.normalize_mac("aa:bb:cc") is None  # Too short

    def test_admin_state_to_bool(self):
        """Test admin state to boolean conversion."""
        engine = LLMDiffEngine()
        assert engine.admin_state_to_bool("up") is True
        assert engine.admin_state_to_bool("UP") is True
        assert engine.admin_state_to_bool("down") is False
        assert engine.admin_state_to_bool("DOWN") is False
        assert engine.admin_state_to_bool(True) is True
        assert engine.admin_state_to_bool(False) is False
        assert engine.admin_state_to_bool(1) is True
        assert engine.admin_state_to_bool(0) is False
        assert engine.admin_state_to_bool(None) is True  # Default enabled
