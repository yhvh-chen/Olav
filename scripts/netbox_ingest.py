"""NetBox inventory ingestion script.

Reads config/inventory.csv and idempotently ensures baseline objects and devices exist:
- Site(s)
- Device Roles
- Manufacturer (generic if not provided)
- Device Types
- Platforms
- Devices (with status)
- Optional management IP (creates interface 'Mgmt' + IP address, assigns primary_ip4)

Modes:
- Bootstrap Mode: Auto-run if NetBox has 0 devices (first-time setup)
- Skip Mode: Skip if NetBox has devices (set NETBOX_INGEST_FORCE=true to override)
- Force Mode: Always import (NETBOX_INGEST_FORCE=true)

Exit codes:
0 success
1 env missing
2 connectivity/auth failure
3 CSV parse error
4 partial failures (some rows failed)
99 skipped (NetBox already initialized)

This script is SAFE to re-run; existing objects are not duplicated.

CSV path resolution order:
1) CLI argument: --csv
2) INVENTORY_CSV_PATH env var
3) NETBOX_CSV_PATH env var (backward compatibility)
4) Default: config/inventory.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import ipaddress
from typing import Dict, Any, List, Optional
import requests

BASE_TIMEOUT = 15
HEADERS: Dict[str, str] = {}

TAG_NAME = os.getenv("NETBOX_DEVICE_TAG", "olav-managed")
AUTO_TAG_ALL = os.getenv("SUZIEQ_AUTO_TAG_ALL", "false").lower() == "true"

API = {
    "sites": "/api/dcim/sites/",
    "device_roles": "/api/dcim/device-roles/",
    "manufacturers": "/api/dcim/manufacturers/",
    "device_types": "/api/dcim/device-types/",
    "platforms": "/api/dcim/platforms/",
    "devices": "/api/dcim/devices/",
    "interfaces": "/api/dcim/interfaces/",
    "ip_addresses": "/api/ipam/ip-addresses/",
    "tags": "/api/extras/tags/",
}

REQUIRED_COLUMNS = ["name", "device_role", "device_type", "platform", "site", "status", "mgmt_interface", "mgmt_address"]
GENERIC_MANUFACTURER = {"name": "generic", "slug": "generic"}
MAX_RETRIES = 3
SENTINEL_DIR = "data/bootstrap"

def _ensure_sentinel_dir() -> None:
    try:
        os.makedirs(SENTINEL_DIR, exist_ok=True)
    except Exception:
        pass

def _write_sentinel(filename: str, payload: Dict[str, Any]) -> None:
    _ensure_sentinel_dir()
    path = os.path.join(SENTINEL_DIR, filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(payload))
    except Exception:
        pass

def fail(code: int, msg: str, context: Optional[Dict[str, Any]] = None) -> None:
    print({"success": False, "code": code, "error": msg, "context": context or {}})
    sys.exit(code)

def env() -> str:
    url = os.getenv("NETBOX_URL")
    token = os.getenv("NETBOX_TOKEN")
    if not url or not token:
        fail(1, "Missing NETBOX_URL or NETBOX_TOKEN")
    HEADERS.update({"Authorization": f"Token {token}", "Content-Type": "application/json"})
    return url.rstrip("/")

def get(base: str, endpoint: str, params: Dict[str, Any]) -> requests.Response:
    return requests.get(base + endpoint, headers=HEADERS, params=params, timeout=BASE_TIMEOUT)

def post(base: str, endpoint: str, json_body: Dict[str, Any]) -> requests.Response:
    return requests.post(base + endpoint, headers=HEADERS, json=json_body, timeout=BASE_TIMEOUT)

def post_with_retry(base: str, endpoint: str, json_body: Dict[str, Any]) -> requests.Response:
    """POST with simple retry for transient server-side errors (5xx)."""
    attempt = 0
    while True:
        resp = post(base, endpoint, json_body)
        # Retry only on 5xx
        if resp.status_code >= 500 and attempt < MAX_RETRIES:
            attempt += 1
            continue
        return resp

def ensure_object(base: str, endpoint: str, unique_field: str, payload: Dict[str, Any]) -> int:
    resp = get(base, endpoint, {unique_field: payload[unique_field]})
    if resp.status_code in (401,403): fail(2, f"Auth failure listing {endpoint}")
    if resp.status_code >= 500: fail(2, f"Server error listing {endpoint}: {resp.status_code}")
    data = resp.json()
    if data.get("count",0) > 0:
        return data["results"][0]["id"]
    create = post(base, endpoint, payload)
    if create.status_code not in (200,201):
        fail(2, f"Failed creating {endpoint} status={create.status_code}", {"payload": payload, "text": create.text[:200]})
    return create.json()["id"]

def parse_csv(path: str) -> List[Dict[str,str]]:
    if not os.path.exists(path):
        fail(3, f"Inventory file not found: {path}")
    rows: List[Dict[str,str]] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(filter(lambda l: not l.startswith("#"), f))
        fieldnames = reader.fieldnames or []  # type: ignore
        # Backward compatibility: if legacy ip_address column present, map to mgmt_address and default interface name
        compat_map = {}
        if "ip_address" in fieldnames and "mgmt_address" not in fieldnames:
            compat_map["mgmt_address"] = "ip_address"
        missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames and c not in compat_map]
        if missing:
            fail(3, f"Inventory CSV missing columns: {missing}")
        for r in reader:
            if not r.get("name"):
                continue
            row: Dict[str,str] = {}
            for k in REQUIRED_COLUMNS:
                if k in r:
                    row[k] = r.get(k, "").strip()
                elif k in compat_map:
                    row[k] = r.get(compat_map[k], "").strip()
            # Provide default mgmt_interface if missing (legacy mode)
            if not row.get("mgmt_interface"):
                row["mgmt_interface"] = "Mgmt"
            rows.append(row)
    return rows

def ensure_baseline(base: str, rows: List[Dict[str,str]]) -> Dict[str,int]:
    ids: Dict[str,int] = {}
    # Manufacturer
    manuf_id = ensure_object(base, API["manufacturers"], "name", GENERIC_MANUFACTURER)
    ids["manufacturer"] = manuf_id
    # Sites
    for site in sorted({r["site"] for r in rows}):
        ids[f"site:{site}"] = ensure_object(base, API["sites"], "name", {"name": site, "slug": site})
    # Roles
    for role in sorted({r["device_role"] for r in rows}):
        ids[f"role:{role}"] = ensure_object(base, API["device_roles"], "name", {"name": role, "slug": role})
    # Device Types
    for dtype in sorted({r["device_type"] for r in rows}):
        ids[f"dtype:{dtype}"] = ensure_object(base, API["device_types"], "model", {"model": dtype, "slug": dtype, "manufacturer": manuf_id})
    # Platforms
    for plat in sorted({r["platform"] for r in rows}):
        ids[f"platform:{plat}"] = ensure_object(base, API["platforms"], "name", {"name": plat, "slug": plat})

    # Tags (optional)
    # If AUTO_TAG_ALL is enabled, ensure the tag exists before creating devices referencing it.
    if AUTO_TAG_ALL and TAG_NAME:
        tag_slug = TAG_NAME.strip().lower()
        if tag_slug:
            ids["tag:device"] = ensure_object(
                base,
                API["tags"],
                "slug",
                {"name": TAG_NAME, "slug": tag_slug},
            )
    return ids


def _tag_all_existing_devices(base: str, tag_id: int) -> Dict[str, Any]:
    """Ensure all existing devices include the given NetBox tag ID.

    This is used when NetBox already has devices and we are in skip mode,
    but SUZIEQ_AUTO_TAG_ALL=true indicates the operator wants devices tagged.
    """
    updated = 0
    skipped = 0
    errors = 0

    offset = 0
    limit = 100
    while True:
        resp = get(base, API["devices"], {"limit": limit, "offset": offset})
        if resp.status_code in (401, 403):
            fail(2, "Auth failure listing devices")
        if resp.status_code >= 500:
            fail(2, f"Server error listing devices: {resp.status_code}")

        payload = resp.json()
        results = payload.get("results", [])
        if not results:
            break

        for dev in results:
            device_id = dev.get("id")
            device_name = dev.get("name")
            current_tags = [t.get("id") for t in (dev.get("tags") or []) if isinstance(t, dict)]
            current_tags = [t for t in current_tags if isinstance(t, int)]

            if tag_id in current_tags:
                skipped += 1
                continue

            new_tags = current_tags + [tag_id]
            patch_resp = requests.patch(
                base + API["devices"] + f"{device_id}/",
                headers=HEADERS,
                json={"tags": new_tags},
                timeout=BASE_TIMEOUT,
            )
            if patch_resp.status_code not in (200, 201):
                errors += 1
                print({
                    "success": False,
                    "code": 4,
                    "error": "Failed to tag device",
                    "context": {
                        "device": device_name,
                        "status": patch_resp.status_code,
                        "text": (patch_resp.text or "")[:200],
                    },
                })
                continue

            updated += 1

        offset += len(results)
        if payload.get("next") is None:
            break

    return {"updated": updated, "skipped": skipped, "errors": errors}

def ensure_device(base: str, row: Dict[str,str], ids: Dict[str,int]) -> Dict[str,Any]:
    # Look up existing device
    resp = get(base, API["devices"], {"name": row["name"]})
    if resp.status_code >= 500: fail(2, f"Server error listing devices: {resp.status_code}")
    data = resp.json()
    if data.get("count",0) > 0:
        device_id = data["results"][0]["id"]
        # Ensure management interface/IP if mgmt_address provided
        return _ensure_mgmt(base, device_id, row)
    body = {
        "name": row["name"],
        "device_type": ids[f"dtype:{row['device_type']}"] ,
        # NetBox DeviceSerializer expects field name 'role' not 'device_role'
        "role": ids[f"role:{row['device_role']}"] ,
        "site": ids[f"site:{row['site']}"] ,
        "status": row["status"],
        "platform": ids[f"platform:{row['platform']}"] ,
    }

    if AUTO_TAG_ALL and TAG_NAME:
        tag_slug = TAG_NAME.strip().lower()
        if tag_slug:
            body["tags"] = [{"name": TAG_NAME, "slug": tag_slug}]
    create = post_with_retry(base, API["devices"], body)
    if create.status_code not in (200,201):
        # Capture a bit more structured error information if available
        err_json: Any = None
        try:
            err_json = create.json()
        except Exception:
            pass
        return {
            "name": row["name"],
            "status": "error",
            "code": create.status_code,
            "text": create.text[:160],
            "errors": err_json if isinstance(err_json, dict) else None,
            "payload": body,
        }
    device_id = create.json()["id"]
    return _ensure_mgmt(base, device_id, row, created=True)

def _ensure_mgmt(base: str, device_id: int, row: Dict[str,str], created: bool=False) -> Dict[str,Any]:
    ip = row.get("mgmt_address")
    iface_name = row.get("mgmt_interface", "Mgmt")
    if not ip:
        return {"name": row["name"], "status": "created" if created else "exists", "note": "no mgmt ip"}
    try:
        ipaddress.ip_interface(ip)
    except ValueError:
        return {"name": row["name"], "status": "created" if created else "exists", "note": "invalid mgmt ip"}
    # Check if interface exists
    iface_lookup = get(base, API["interfaces"], {"device_id": device_id, "name": iface_name})
    if iface_lookup.status_code >= 500:
        return {"name": row["name"], "status": "error", "code": iface_lookup.status_code, "text": "iface list"}
    iface_data = iface_lookup.json()
    if iface_data.get("count",0) > 0:
        iface_id = iface_data["results"][0]["id"]
    else:
        iface_payload = {"device": device_id, "name": iface_name, "type": "virtual"}
        iface_resp = post_with_retry(base, API["interfaces"], iface_payload)
        if iface_resp.status_code not in (200,201):
            return {"name": row["name"], "status": "created" if created else "exists", "note": "iface failed"}
        iface_id = iface_resp.json()["id"]
    # Check if IP already assigned
    ip_lookup = get(base, API["ip_addresses"], {"address": ip})
    if ip_lookup.status_code >= 500:
        return {"name": row["name"], "status": "error", "code": ip_lookup.status_code, "text": "ip list"}
    ip_data = ip_lookup.json()
    if ip_data.get("count",0) > 0:
        ip_id = ip_data["results"][0]["id"]
    else:
        ip_payload = {"address": ip, "status": "active", "assigned_object_type": "dcim.interface", "assigned_object_id": iface_id}
        ip_resp = post_with_retry(base, API["ip_addresses"], ip_payload)
        if ip_resp.status_code not in (200,201):
            return {"name": row["name"], "status": "created" if created else "exists", "note": "ip failed"}
        ip_id = ip_resp.json()["id"]
    # Patch device primary_ip4
    patch_resp = requests.patch(base + API["devices"] + f"{device_id}/", headers=HEADERS, json={"primary_ip4": ip_id}, timeout=BASE_TIMEOUT)
    if patch_resp.status_code not in (200,201):
        return {"name": row["name"], "status": "created" if created else "exists", "note": "primary_ip4 patch failed"}
    return {"name": row["name"], "status": "created" if created else "exists"}

def main() -> None:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument(
        "--csv",
        dest="csv_path",
        default=None,
        help="Path to inventory CSV (default: config/inventory.csv)",
    )
    args = parser.parse_args()

    base = env()
    
    # Mode detection: Check if NetBox already has devices
    force_mode = os.getenv("NETBOX_INGEST_FORCE", "false").lower() == "true"
    
    try:
        device_check = get(base, API["devices"], {"limit": 1})
        device_count = device_check.json().get("count", 0)
        
        if device_count > 0 and not force_mode:
            tag_result: Dict[str, Any] | None = None
            tag_slug = (TAG_NAME or "").strip().lower()

            # Even if we skip import, optionally ensure tag exists and tag all existing devices.
            if AUTO_TAG_ALL and tag_slug:
                tag_id = ensure_object(base, API["tags"], "slug", {"name": TAG_NAME, "slug": tag_slug})
                tag_result = _tag_all_existing_devices(base, tag_id)

            summary = {
                "success": True,
                "code": 99,
                "mode": "skip",
                "message": (
                    f"NetBox already has {device_count} devices. Skipping import. "
                    "Set NETBOX_INGEST_FORCE=true to override."
                ),
                "auto_tag": AUTO_TAG_ALL,
                "tag": TAG_NAME,
                "tag_result": tag_result,
                "devices": [],
            }
            print(summary)
            _write_sentinel("inventory.ok", summary)
            sys.exit(99)
        
        mode = "force" if device_count > 0 else "bootstrap"
        if mode == "force":
            print(f"Force mode enabled. NetBox has {device_count} devices but importing anyway.")
        else:
            print(f"Bootstrap mode: NetBox is empty. Importing devices from CSV.")
            
    except Exception as e:
        # If we can't check, assume bootstrap mode (safer for init containers)
        print(f"Warning: Could not check NetBox device count ({e}). Proceeding with import.")
        mode = "bootstrap"
    
    csv_path = (
        args.csv_path
        or os.getenv("INVENTORY_CSV_PATH")
        or os.getenv("NETBOX_CSV_PATH")
        or "config/inventory.csv"
    )
    rows = parse_csv(csv_path)
    ids = ensure_baseline(base, rows)
    results: List[Dict[str,Any]] = []
    errors = 0
    for r in rows:
        res = ensure_device(base, r, ids)
        results.append(res)
        if res.get("status") == "error":
            errors += 1
    summary = {"success": errors == 0, "code": 0 if errors == 0 else 4, "mode": mode, "devices": results}
    print(summary)
    # Sentinel writing for observability by init container and external monitors
    if errors == 0:
        _write_sentinel("inventory.ok", summary)
    else:
        _write_sentinel("inventory.error", summary)
    if errors:
        sys.exit(4)

if __name__ == "__main__":
    main()
