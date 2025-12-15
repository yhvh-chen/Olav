"""Debug helper: delete Loopback11 on R1 via NETCONF routing and verify via CLI show.

Usage (host):
  docker-compose -f docker-compose.yml -f docker-compose.dev.yml exec -T olav-server uv run python scripts/debug_delete_lo11.py

This script is intentionally small and prints results to stdout.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure repo root + src are importable when executed inside Docker.
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))


async def main() -> None:
    from olav.tools import ToolRegistry  # noqa: F401 (triggers tool registration)
    from olav.tools.base import ToolRegistry as _TR
    from olav.tools.nornir_tool import DeviceConfigRouter
    from config.settings import settings

    router = DeviceConfigRouter()
    print("--- transport ---")
    print("R1 transport:", router.get_device_transport("R1"))

    print("--- netconf capabilities (R1) ---")
    try:
        from ncclient import manager

        host = router.sandbox.nr.inventory.hosts["R1"]
        hostname = host.hostname or host.name
        port = int(host.data.get("netconf_port") or 830)

        with manager.connect(
            host=hostname,
            port=port,
            username=settings.device_username,
            password=settings.device_password,
            hostkey_verify=False,
            allow_agent=False,
            look_for_keys=False,
            timeout=10,
        ) as m:
            caps = list(m.server_capabilities)
            oc = [c for c in caps if "openconfig" in c.lower()]
            print(f"host={hostname} port={port} openconfig_caps={len(oc)}")
            for c in oc[:25]:
                print("  ", c)

            print("--- openconfig get-config (Loopback11) ---")
            # Use a subtree filter to avoid requiring the device to support the XPATH capability.
            flt = (
                "subtree",
                """
                <interfaces xmlns=\"http://openconfig.net/yang/interfaces\">
                  <interface>
                    <name>Loopback11</name>
                  </interface>
                </interfaces>
                """.strip(),
            )
            try:
                reply = m.get_config(source="running", filter=flt)
                print(str(reply)[:1200])
            except Exception as e:
                print("get_config_failed:", repr(e))
    except Exception as e:
        print("capability_check_failed:", repr(e))

    print("--- delete Loopback11 via NETCONF/OpenConfig ---")
    result = await router.execute_config(
        device="R1",
        config_commands=["no interface Loopback11"],
        interface="Loopback11",
        operation="delete",
    )
    print(result)

    print("--- verify via CLI show (should be empty) ---")
    cli = _TR.get_tool("cli_execute")
    if cli is None:
        raise RuntimeError("cli_execute not registered")

    show = await cli.execute(device="R1", command="show ip interface brief | include Loopback11")
    print({"success": show.error is None, "error": show.error, "output": show.data})


if __name__ == "__main__":
    asyncio.run(main())
