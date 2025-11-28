"""
Unit tests for SchemaMapper - Schema-Aware Dynamic Field Mapping.
"""

import pytest

from olav.sync.schema_mapper import (
    FieldMapping,
    SchemaMapper,
    SchemaMappingResult,
    TransformType,
    get_schema_mapper,
)


class TestSchemaMapper:
    """Tests for SchemaMapper class."""

    def test_singleton_pattern(self):
        """Test that get_schema_mapper returns singleton."""
        mapper1 = get_schema_mapper()
        mapper2 = get_schema_mapper()
        assert mapper1 is mapper2

    def test_map_interface_type_loopback(self):
        """Test loopback interface type mapping."""
        mapper = SchemaMapper()
        assert mapper.map_interface_type("loopback") == "virtual"
        assert mapper.map_interface_type("Loopback") == "virtual"
        assert mapper.map_interface_type(None, "Loopback0") == "virtual"
        assert mapper.map_interface_type(None, "lo0") == "virtual"

    def test_map_interface_type_ethernet(self):
        """Test ethernet interface type mapping."""
        mapper = SchemaMapper()
        assert mapper.map_interface_type("ethernet") == "1000base-t"
        assert mapper.map_interface_type("gigabit") == "1000base-t"
        assert mapper.map_interface_type(None, "GigabitEthernet0/0") == "1000base-t"
        assert mapper.map_interface_type(None, "eth0") == "1000base-t"

    def test_map_interface_type_vlan(self):
        """Test VLAN interface type mapping."""
        mapper = SchemaMapper()
        assert mapper.map_interface_type("vlan") == "virtual"
        assert mapper.map_interface_type("svi") == "virtual"
        assert mapper.map_interface_type(None, "Vlan100") == "virtual"

    def test_map_interface_type_lag(self):
        """Test LAG interface type mapping."""
        mapper = SchemaMapper()
        assert mapper.map_interface_type("lag") == "lag"
        assert mapper.map_interface_type("bond") == "lag"
        assert mapper.map_interface_type("port-channel") == "lag"

    def test_map_interface_type_unknown(self):
        """Test unknown interface type returns 'other'."""
        mapper = SchemaMapper()
        assert mapper.map_interface_type("unknown") == "other"
        assert mapper.map_interface_type(None, "weird0") == "other"
        assert mapper.map_interface_type(None, None) == "other"

    def test_normalize_speed_gbps(self):
        """Test speed normalization from Gbps."""
        mapper = SchemaMapper()
        # < 1000 = assume Gbps
        assert mapper._normalize_speed(1) == 1_000_000  # 1 Gbps = 1M kbps
        assert mapper._normalize_speed(10) == 10_000_000  # 10 Gbps
        assert mapper._normalize_speed(100) == 100_000_000  # 100 Gbps

    def test_normalize_speed_mbps(self):
        """Test speed normalization from Mbps."""
        mapper = SchemaMapper()
        # 1000-999999 = assume Mbps
        assert mapper._normalize_speed(1000) == 1_000_000  # 1000 Mbps = 1M kbps
        assert mapper._normalize_speed(10000) == 10_000_000  # 10000 Mbps

    def test_normalize_speed_kbps(self):
        """Test speed normalization from kbps (passthrough)."""
        mapper = SchemaMapper()
        # 1M-999M = assume already kbps
        assert mapper._normalize_speed(1_000_000) == 1_000_000
        assert mapper._normalize_speed(10_000_000) == 10_000_000

    def test_normalize_speed_bps(self):
        """Test speed normalization from bps."""
        mapper = SchemaMapper()
        # >= 1B = assume bps
        assert mapper._normalize_speed(1_000_000_000) == 1_000_000  # 1 Gbps in bps

    def test_normalize_speed_invalid(self):
        """Test speed normalization with invalid values."""
        mapper = SchemaMapper()
        assert mapper._normalize_speed(None) is None
        assert mapper._normalize_speed(0) is None
        assert mapper._normalize_speed(-1) is None
        assert mapper._normalize_speed("invalid") is None

    def test_normalize_mac_colon_format(self):
        """Test MAC normalization from colon format."""
        mapper = SchemaMapper()
        assert mapper._normalize_mac("aa:bb:cc:dd:ee:ff") == "AA:BB:CC:DD:EE:FF"
        assert mapper._normalize_mac("AA:BB:CC:DD:EE:FF") == "AA:BB:CC:DD:EE:FF"

    def test_normalize_mac_dash_format(self):
        """Test MAC normalization from dash format."""
        mapper = SchemaMapper()
        assert mapper._normalize_mac("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"

    def test_normalize_mac_dot_format(self):
        """Test MAC normalization from Cisco dot format."""
        mapper = SchemaMapper()
        assert mapper._normalize_mac("aabb.ccdd.eeff") == "AA:BB:CC:DD:EE:FF"

    def test_normalize_mac_invalid(self):
        """Test MAC normalization with invalid values."""
        mapper = SchemaMapper()
        assert mapper._normalize_mac(None) is None
        assert mapper._normalize_mac("") is None
        assert mapper._normalize_mac("invalid") is None
        assert mapper._normalize_mac("aa:bb:cc") is None  # Too short

    def test_get_default_mapping_interface(self):
        """Test default mapping for interfaces."""
        mapper = SchemaMapper()
        mapping = mapper._get_default_mapping("interface", "suzieq", "netbox")

        assert mapping.entity_type == "interface"
        assert mapping.source_system == "suzieq"
        assert mapping.target_system == "netbox"
        assert len(mapping.field_mappings) > 0
        assert len(mapping.type_mappings) > 0

        # Check specific field mappings
        field_names = [fm.source_field for fm in mapping.field_mappings]
        assert "ifname" in field_names
        assert "adminState" in field_names
        assert "type" in field_names

    def test_apply_transform_direct(self):
        """Test direct transform (no change)."""
        mapper = SchemaMapper()
        result = mapper._apply_transform("test_value", TransformType.DIRECT, {})
        assert result == "test_value"

    def test_apply_transform_boolean(self):
        """Test boolean from up/down transform."""
        mapper = SchemaMapper()
        assert mapper._apply_transform("up", TransformType.BOOLEAN_FROM_UPDOWN, {}) is True
        assert mapper._apply_transform("UP", TransformType.BOOLEAN_FROM_UPDOWN, {}) is True
        assert mapper._apply_transform("down", TransformType.BOOLEAN_FROM_UPDOWN, {}) is False
        assert mapper._apply_transform(1, TransformType.BOOLEAN_FROM_UPDOWN, {}) is True
        assert mapper._apply_transform(0, TransformType.BOOLEAN_FROM_UPDOWN, {}) is False

    def test_apply_transform_type_mapping(self):
        """Test type mapping transform."""
        mapper = SchemaMapper()
        type_map = {"loopback": "virtual", "ethernet": "1000base-t"}

        assert mapper._apply_transform("loopback", TransformType.TYPE_MAPPING, type_map) == "virtual"
        assert mapper._apply_transform("ethernet", TransformType.TYPE_MAPPING, type_map) == "1000base-t"
        assert mapper._apply_transform("unknown", TransformType.TYPE_MAPPING, type_map) == "other"

    def test_apply_mapping(self):
        """Test full mapping application."""
        mapper = SchemaMapper()
        mapping = SchemaMappingResult(
            entity_type="interface",
            source_system="suzieq",
            target_system="netbox",
            field_mappings=[
                FieldMapping(
                    source_field="ifname",
                    target_field="name",
                    transform=TransformType.DIRECT,
                ),
                FieldMapping(
                    source_field="adminState",
                    target_field="enabled",
                    transform=TransformType.BOOLEAN_FROM_UPDOWN,
                ),
                FieldMapping(
                    source_field="type",
                    target_field="type",
                    transform=TransformType.TYPE_MAPPING,
                ),
            ],
            type_mappings={"loopback": "virtual"},
        )

        source_data = {
            "ifname": "Loopback0",
            "adminState": "up",
            "type": "loopback",
        }

        result = mapper.apply_mapping(source_data, mapping)

        assert result["name"] == "Loopback0"
        assert result["enabled"] is True
        assert result["type"] == "virtual"


class TestFieldMapping:
    """Tests for FieldMapping model."""

    def test_field_mapping_defaults(self):
        """Test FieldMapping with default values."""
        fm = FieldMapping(source_field="test", target_field="test")
        assert fm.transform == TransformType.DIRECT
        assert fm.description == ""

    def test_field_mapping_with_transform(self):
        """Test FieldMapping with custom transform."""
        fm = FieldMapping(
            source_field="adminState",
            target_field="enabled",
            transform=TransformType.BOOLEAN_FROM_UPDOWN,
            description="SuzieQ up/down to boolean",
        )
        assert fm.transform == TransformType.BOOLEAN_FROM_UPDOWN


class TestSchemaMappingResult:
    """Tests for SchemaMappingResult model."""

    def test_empty_result(self):
        """Test empty mapping result."""
        result = SchemaMappingResult(
            entity_type="interface",
            source_system="suzieq",
            target_system="netbox",
        )
        assert result.field_mappings == []
        assert result.type_mappings == {}
        assert result.unmappable_fields == []
        assert result.cached is False


@pytest.mark.asyncio
async def test_get_mapping_fallback():
    """Test that get_mapping falls back to defaults when LLM unavailable."""
    mapper = SchemaMapper()
    mapper.use_llm = False  # Disable LLM for this test

    mapping = await mapper.get_mapping("interface", "suzieq", "netbox")

    assert mapping.entity_type == "interface"
    assert len(mapping.field_mappings) > 0
    assert "loopback" in mapping.type_mappings


@pytest.mark.asyncio
async def test_get_mapping_caching():
    """Test that mappings are cached."""
    mapper = SchemaMapper()
    mapper.use_llm = False

    # First call
    mapping1 = await mapper.get_mapping("interface", "suzieq", "netbox")
    assert not mapping1.cached

    # Second call should be cached
    mapping2 = await mapper.get_mapping("interface", "suzieq", "netbox")
    assert mapping2.cached
