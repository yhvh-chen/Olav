"""
OpenConfig NETCONF Support Tests

These tests require a live NETCONF-enabled device and are skipped in CI.
For manual testing, set environment variables:
  - NETCONF_HOST: Device hostname/IP
  - NETCONF_PORT: NETCONF port (default: 830)
  - NETCONF_USERNAME: Device username
  - NETCONF_PASSWORD: Device password
"""

import os

import pytest


# Skip all tests in this module if no NETCONF device is configured
pytestmark = pytest.mark.skipif(
    not os.environ.get("NETCONF_HOST"),
    reason="NETCONF device not configured. Set NETCONF_HOST environment variable to enable."
)


@pytest.fixture
def netconf_connection():
    """Create NETCONF connection from environment variables."""
    from ncclient import manager
    
    host = os.environ.get("NETCONF_HOST")
    port = int(os.environ.get("NETCONF_PORT", "830"))
    username = os.environ.get("NETCONF_USERNAME", "admin")
    password = os.environ.get("NETCONF_PASSWORD", "admin")
    
    conn = manager.connect(
        host=host,
        port=port,
        username=username,
        password=password,
        hostkey_verify=False,
        look_for_keys=False,
        allow_agent=False,
    )
    yield conn
    conn.close_session()


def test_get_capabilities(netconf_connection):
    """Test retrieving device capabilities."""
    caps = netconf_connection.server_capabilities
    assert len(caps) > 0, "Device should report at least one capability"


def test_get_running_config(netconf_connection):
    """Test retrieving running configuration."""
    config = netconf_connection.get_config(source="running")
    assert config is not None


def test_openconfig_interfaces_supported(netconf_connection):
    """Test if OpenConfig interfaces model is supported."""
    openconfig_if_cap = None
    for cap in netconf_connection.server_capabilities:
        if "openconfig-interfaces" in cap:
            openconfig_if_cap = cap
            break
    
    # This is informational - device may not support OpenConfig
    if openconfig_if_cap:
        pytest.skip(f"OpenConfig interfaces supported: {openconfig_if_cap}")
    else:
        pytest.skip("OpenConfig interfaces not supported by device")


def test_get_interfaces_state(netconf_connection):
    """Test getting interface state via OpenConfig or native model."""
    from lxml import etree
    
    # Try OpenConfig first
    openconfig_filter = """
    <interfaces xmlns="http://openconfig.net/yang/interfaces">
        <interface>
            <state/>
        </interface>
    </interfaces>
    """
    
    try:
        result = netconf_connection.get(filter=("subtree", openconfig_filter))
        root = etree.fromstring(result.data_xml.encode())
        interfaces = root.findall(".//{http://openconfig.net/yang/interfaces}interface")
        assert len(interfaces) > 0, "Should have at least one interface"
    except Exception:
        # Fall back to native Cisco model
        cisco_filter = """
        <interfaces xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-interfaces-oper">
            <interface/>
        </interfaces>
        """
        result = netconf_connection.get(filter=("subtree", cisco_filter))
        assert result is not None
