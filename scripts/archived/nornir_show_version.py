"""Execute 'show version' on all devices via Nornir + Netmiko.

Demonstrates:
- NetBox inventory integration
- Netmiko connection plugin
- Simple read-only command execution

Env vars required: NETBOX_URL, NETBOX_TOKEN, DEVICE_USERNAME, DEVICE_PASSWORD
"""
from __future__ import annotations

import os
import sys
import json
from typing import Dict, Any

def main() -> None:
    # Env validation
    required = ["NETBOX_URL", "NETBOX_TOKEN", "DEVICE_USERNAME", "DEVICE_PASSWORD"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        print(json.dumps({"success": False, "error": f"Missing env: {missing}"}))
        sys.exit(1)
    
    # Import after env check
    try:
        from nornir import InitNornir
        from nornir_netmiko.tasks import netmiko_send_command
    except ImportError as e:
        print(json.dumps({"success": False, "error": f"Missing dependency: {e}"}))
        sys.exit(1)
    
    # Initialize Nornir
    nb_url = os.getenv("NETBOX_URL", "http://localhost:8080")
    nb_token = os.getenv("NETBOX_TOKEN")
    username = os.getenv("DEVICE_USERNAME")
    password = os.getenv("DEVICE_PASSWORD")
    
    nr = InitNornir(
        config_file="data/generated_configs/nornir_config.yml",
        inventory={
            "plugin": "NetBoxInventory2",
            "options": {
                "nb_url": nb_url,
                "nb_token": nb_token,
                "ssl_verify": False,
                "filter_parameters": {"tag": ["olav-managed"]},
                "defaults": {
                    "username": username,
                    "password": password,
                },
            },
        },
    )
    
    # Execute show version
    print(f"Executing 'show version' on {len(nr.inventory.hosts)} devices...")
    result = nr.run(task=netmiko_send_command, command_string="show version")
    
    # Parse results
    outputs: Dict[str, Any] = {}
    for host, multi_result in result.items():
        if multi_result.failed:
            outputs[host] = {"success": False, "error": str(multi_result.exception)}
        else:
            outputs[host] = {"success": True, "output": multi_result.result}
    
    payload = {
        "success": True,
        "device_count": len(nr.inventory.hosts),
        "results": outputs,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
