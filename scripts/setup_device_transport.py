#!/usr/bin/env python3
"""
Setup device config_transport custom field in NetBox.

This script:
1. Creates the 'config_transport' custom field if it doesn't exist
2. Sets R1, R2 to 'netconf' (OpenConfig capable)
3. Sets other devices to 'cli' (legacy SSH)

Usage:
    uv run python scripts/setup_device_transport.py
"""

import os
import sys

import httpx

# Load settings
NETBOX_URL = os.getenv("NETBOX_URL", "http://localhost:8080")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN", "")

if not NETBOX_TOKEN:
    # Try loading from .env
    from pathlib import Path
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("NETBOX_TOKEN="):
                NETBOX_TOKEN = line.split("=", 1)[1].strip().strip('"\'')
            elif line.startswith("NETBOX_URL="):
                NETBOX_URL = line.split("=", 1)[1].strip().strip('"\'')

if not NETBOX_TOKEN:
    print("Error: NETBOX_TOKEN not set. Please set it in environment or .env file.")
    sys.exit(1)

# Transport assignments
NETCONF_DEVICES = ["R1", "R2"]  # OpenConfig capable (IOS-XE)
CLI_DEVICES = ["R3", "R4", "SW1", "SW2"]  # Legacy CLI only

HEADERS = {
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def get_or_create_custom_field(client: httpx.Client) -> int:
    """Get or create the config_transport custom field.
    
    Returns:
        Custom field ID
    """
    # Check if custom field exists
    resp = client.get(
        f"{NETBOX_URL}/api/extras/custom-fields/",
        params={"name": "config_transport"}
    )
    resp.raise_for_status()
    data = resp.json()
    
    if data["count"] > 0:
        cf_id = data["results"][0]["id"]
        print(f"✓ Custom field 'config_transport' exists (ID: {cf_id})")
        return cf_id
    
    # Create custom field - NetBox 4.x compatible
    print("Creating custom field 'config_transport'...")
    
    cf_payload = {
        "object_types": ["dcim.device"],  # NetBox 4.x uses object_types
        "name": "config_transport",
        "label": "Config Transport",
        "type": "text",  # Use text type for simplicity
        "description": "Configuration transport: netconf, cli, or auto",
        "required": False,
        "ui_visible": "always",
        "ui_editable": "yes",
        "weight": 100,
    }
    
    resp = client.post(
        f"{NETBOX_URL}/api/extras/custom-fields/",
        json=cf_payload
    )
    
    if resp.status_code == 201:
        cf_id = resp.json()["id"]
        print(f"✓ Created custom field 'config_transport' (ID: {cf_id})")
        return cf_id
    elif resp.status_code == 400 and "already exists" in resp.text.lower():
        print("✓ Custom field already exists (different query)")
        return 0
    else:
        print(f"Warning: Could not create custom field: {resp.status_code} - {resp.text}")
        print("Continuing anyway - will try to set values directly")
        return 0


def get_or_create_choice_set(client: httpx.Client) -> int | None:
    """Get or create the choice set for config_transport values."""
    # Check if choice set exists
    resp = client.get(
        f"{NETBOX_URL}/api/extras/custom-field-choice-sets/",
        params={"name": "config_transport_choices"}
    )
    resp.raise_for_status()
    data = resp.json()
    
    if data["count"] > 0:
        cs_id = data["results"][0]["id"]
        print(f"✓ Choice set exists (ID: {cs_id})")
        return cs_id
    
    # Create choice set
    print("Creating choice set for config_transport...")
    cs_payload = {
        "name": "config_transport_choices",
        "description": "Transport options for device configuration",
        "extra_choices": [
            ["auto", "Auto (try NETCONF first)"],
            ["netconf", "NETCONF (OpenConfig)"],
            ["cli", "CLI (SSH)"],
        ]
    }
    
    resp = client.post(
        f"{NETBOX_URL}/api/extras/custom-field-choice-sets/",
        json=cs_payload
    )
    
    if resp.status_code == 201:
        cs_id = resp.json()["id"]
        print(f"✓ Created choice set (ID: {cs_id})")
        return cs_id
    else:
        print(f"Note: Could not create choice set: {resp.status_code}")
        return None


def set_device_transport(client: httpx.Client, device_name: str, transport: str) -> bool:
    """Set config_transport for a device.
    
    Args:
        client: HTTP client
        device_name: Device hostname
        transport: 'netconf', 'cli', or 'auto'
        
    Returns:
        True if successful
    """
    # Get device ID
    resp = client.get(
        f"{NETBOX_URL}/api/dcim/devices/",
        params={"name": device_name}
    )
    resp.raise_for_status()
    data = resp.json()
    
    if data["count"] == 0:
        print(f"  ⚠ Device '{device_name}' not found in NetBox")
        return False
    
    device_id = data["results"][0]["id"]
    current_cf = data["results"][0].get("custom_fields", {})
    current_transport = current_cf.get("config_transport", "not set")
    
    # Update device custom field
    resp = client.patch(
        f"{NETBOX_URL}/api/dcim/devices/{device_id}/",
        json={
            "custom_fields": {
                "config_transport": transport
            }
        }
    )
    
    if resp.status_code == 200:
        print(f"  ✓ {device_name}: {current_transport} → {transport}")
        return True
    else:
        print(f"  ✗ {device_name}: Failed to update - {resp.status_code}: {resp.text}")
        return False


def main():
    print("=" * 60)
    print("NetBox Device Transport Configuration")
    print("=" * 60)
    print(f"NetBox URL: {NETBOX_URL}")
    print()
    
    with httpx.Client(headers=HEADERS, timeout=30.0, verify=False) as client:
        # Test connection
        try:
            resp = client.get(f"{NETBOX_URL}/api/")
            resp.raise_for_status()
            print("✓ Connected to NetBox API")
        except Exception as e:
            print(f"✗ Failed to connect to NetBox: {e}")
            sys.exit(1)
        
        print()
        print("Step 1: Setting up custom field...")
        print("-" * 40)
        get_or_create_custom_field(client)
        
        print()
        print("Step 2: Configuring NETCONF devices (OpenConfig)...")
        print("-" * 40)
        for device in NETCONF_DEVICES:
            set_device_transport(client, device, "netconf")
        
        print()
        print("Step 3: Configuring CLI devices (Legacy SSH)...")
        print("-" * 40)
        for device in CLI_DEVICES:
            set_device_transport(client, device, "cli")
        
        print()
        print("=" * 60)
        print("Configuration complete!")
        print()
        print("Summary:")
        print(f"  NETCONF (OpenConfig): {', '.join(NETCONF_DEVICES)}")
        print(f"  CLI (SSH):            {', '.join(CLI_DEVICES)}")
        print()
        print("The device_config tool will now automatically route:")
        print("  - R1, R2 → NETCONF/OpenConfig")
        print("  - R3, R4, SW1, SW2 → CLI/SSH")
        print("=" * 60)


if __name__ == "__main__":
    main()
