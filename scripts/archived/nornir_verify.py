"""Nornir connectivity verification script.

Attempts to load hosts from NetBox and perform a basic connectivity test
using TCP socket (port 22 by default) if Nornir is unavailable. If Nornir
is installed and NetBox inventory plugin present, runs a simple Nornir task
to list host names.

Env vars required: NETBOX_URL, NETBOX_TOKEN

Exit codes:
0 success (even if hosts unreachable, script returns list)
1 missing env
2 inventory fetch error
"""
from __future__ import annotations

import os
import sys
import socket
import json
from typing import Dict, Any, List
import requests

PORT = 22
TIMEOUT = 2

def fail(code: int, msg: str) -> None:
    print(json.dumps({"success": False, "code": code, "error": msg}, ensure_ascii=False))
    sys.exit(code)

def env() -> Dict[str,str]:
    url = os.getenv("NETBOX_URL")
    token = os.getenv("NETBOX_TOKEN")
    if not url or not token:
        fail(1, "Missing NETBOX_URL or NETBOX_TOKEN")
    return {"url": url.rstrip('/'), "token": token}

def fetch_devices(ctx: Dict[str,str]) -> List[Dict[str, Any]]:
    devices: List[Dict[str,Any]] = []
    offset = 0
    limit = 100
    headers = {"Authorization": f"Token {ctx['token']}", "Accept": "application/json"}
    while True:
        r = requests.get(f"{ctx['url']}/api/dcim/devices/", params={"limit": limit, "offset": offset}, headers=headers, timeout=10)
        if r.status_code >= 400:
            fail(2, f"Device list failed {r.status_code}")
        data = r.json()
        devices.extend(data.get("results", []))
        if len(data.get("results", [])) < limit:
            break
        offset += limit
    return devices

def try_nornir() -> Any:
    try:
        from nornir import InitNornir  # type: ignore
        from nornir.core.inventory import Defaults
    except Exception:
        return None
    config_path = "data/generated_configs/nornir_config.yml"
    if not os.path.exists(config_path):
        return None
    # Override config values from environment
    nb_url = os.getenv("NETBOX_URL", "http://netbox:8080")
    nb_token = os.getenv("NETBOX_TOKEN", "")
    username = os.getenv("DEVICE_USERNAME", "admin")
    password = os.getenv("DEVICE_PASSWORD", "")
    
    nr = InitNornir(
        config_file=config_path,
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
    return nr

def tcp_check(ip: str, port: int = PORT) -> bool:
    try:
        host = ip.split('/')[0]
        with socket.create_connection((host, port), timeout=TIMEOUT):
            return True
    except Exception:
        return False

def main() -> None:
    ctx = env()
    devices = fetch_devices(ctx)
    # Collect management IP from primary_ip4 if present
    results: List[Dict[str, Any]] = []
    for d in devices:
        primary_ip = d.get("primary_ip4", {})
        address = primary_ip.get("address") if isinstance(primary_ip, dict) else None
        reach = tcp_check(address) if address else False
        results.append({"name": d.get("name"), "mgmt_ip": address, "reachable_tcp22": reach})

    nr = try_nornir()
    nornir_hosts = []
    if nr:
        nornir_hosts = list(nr.inventory.hosts.keys())

    payload = {
        "success": True,
        "code": 0,
        "device_count": len(devices),
        "nornir_hosts": nornir_hosts,
        "devices": results,
        "nornir_active": bool(nr),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()