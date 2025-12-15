"""NetBox cleanup script.

Deletes existing devices and their management IP addresses to reset inventory before re-running init.
Only uses environment variables NETBOX_URL and NETBOX_TOKEN.

Exit codes:
0 - Success
1 - Missing env vars
2 - API auth/connectivity failure
3 - Deletion errors occurred (partial failure)

Safety:
- Deletes *all* devices returned by /api/dcim/devices/ (not filtered)
- Deletes IP addresses first to avoid dangling assignments
- Leaves sites, roles, tags so baseline remains available (auto-create logic will skip existing)
"""
from __future__ import annotations

import os
import sys
import requests
from typing import Dict, Any, List

TIMEOUT = 15
HEADERS: Dict[str,str] = {}
BASE: str = ""

API = {
    "devices": "/api/dcim/devices/",
    "ip_addresses": "/api/ipam/ip-addresses/",
}

def fail(code: int, msg: str, context: Dict[str, Any] | None = None) -> None:
    print({"success": False, "code": code, "error": msg, "context": context or {}})
    sys.exit(code)

def env() -> None:
    global BASE
    url = os.getenv("NETBOX_URL")
    token = os.getenv("NETBOX_TOKEN")
    if not url or not token:
        fail(1, "Missing NETBOX_URL or NETBOX_TOKEN")
    BASE = url.rstrip("/")
    HEADERS.update({"Authorization": f"Token {token}", "Content-Type": "application/json"})


def list_all(endpoint: str) -> List[Dict[str, Any]]:
    results: List[Dict[str,Any]] = []
    limit = 100
    offset = 0
    while True:
        resp = requests.get(f"{BASE}{endpoint}", headers=HEADERS, params={"limit": limit, "offset": offset}, timeout=TIMEOUT)
        if resp.status_code in (401,403):
            fail(2, f"Auth failure listing {endpoint}")
        if resp.status_code >= 500:
            fail(2, f"Server error {resp.status_code} listing {endpoint}")
        data = resp.json()
        batch = data.get("results", [])
        results.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return results


def delete(endpoint: str, obj_id: int) -> bool:
    resp = requests.delete(f"{BASE}{endpoint}{obj_id}/", headers=HEADERS, timeout=TIMEOUT)
    if resp.status_code in (204, 200):
        return True
    return False


def main() -> None:
    env()
    # Delete IP addresses first (not strictly required but safer)
    ip_addrs = list_all(API["ip_addresses"])
    ip_errors = 0
    for ip in ip_addrs:
        if not delete(API["ip_addresses"], ip["id"]):
            ip_errors += 1
    devices = list_all(API["devices"])
    dev_errors = 0
    for dev in devices:
        if not delete(API["devices"], dev["id"]):
            dev_errors += 1
    success = (ip_errors == 0 and dev_errors == 0)
    summary = {
        "success": success,
        "code": 0 if success else 3,
        "deleted_devices": len(devices) - dev_errors,
        "device_delete_errors": dev_errors,
        "deleted_ip_addresses": len(ip_addrs) - ip_errors,
        "ip_delete_errors": ip_errors,
    }
    print(summary)
    if not success:
        sys.exit(3)

if __name__ == "__main__":
    main()
