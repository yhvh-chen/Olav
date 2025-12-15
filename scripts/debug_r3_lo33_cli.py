"""Debug helper: ensure R3 uses CLI transport; add/delete Loopback33; verify via show.

Usage (host):
  docker-compose -f docker-compose.yml -f docker-compose.dev.yml exec -T olav-server uv run python scripts/debug_r3_lo33_cli.py

Expected:
- Transport decision for R3 is 'cli'
- Add operation returns transport_used='cli'
- Delete operation returns transport_used='cli'
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))


async def main() -> None:
    # Trigger tool registration
    from olav.tools import ToolRegistry  # noqa: F401
    from olav.tools.base import ToolRegistry as _TR
    from olav.tools.nornir_tool import DeviceConfigRouter

    router = DeviceConfigRouter()

    print("--- transport ---")
    print("R3 transport:", router.get_device_transport("R3"))

    cli = _TR.get_tool("cli_execute")
    if cli is None:
        raise RuntimeError("cli_execute not registered")

    async def show_lo33(label: str) -> None:
        res = await cli.execute(device="R3", command="show ip interface brief | include Loopback33")
        print(label, {"success": res.error is None, "error": res.error, "output": res.data})

    print("--- precheck ---")
    await show_lo33("pre")

    print("--- add Loopback33 via device_config ---")
    add_result = await router.execute_config(
        device="R3",
        interface="Loopback33",
        operation="merge",
        config_commands=[
            "interface Loopback33",
            "ip address 33.33.33.33 255.255.255.255",
            "no shutdown",
        ],
    )
    print(add_result)

    print("--- verify add via CLI show ---")
    await show_lo33("after_add")

    print("--- delete Loopback33 via device_config ---")
    del_result = await router.execute_config(
        device="R3",
        interface="Loopback33",
        operation="delete",
        config_commands=["no interface Loopback33"],
    )
    print(del_result)

    print("--- verify delete via CLI show ---")
    await show_lo33("after_delete")


if __name__ == "__main__":
    asyncio.run(main())
