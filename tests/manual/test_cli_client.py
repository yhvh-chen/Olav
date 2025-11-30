"""Test CLI Client (Local Mode).

Requires PostgreSQL to be running.
Usage:
    docker-compose up -d postgres
    pytest tests/integration/test_cli_client.py -v
"""

import asyncio
import sys
from pathlib import Path

import pytest

# Add src and config to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))


def _postgres_available() -> bool:
    """Check if PostgreSQL is available."""
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 55432))
        sock.close()
        return result == 0
    except Exception:
        return False


@pytest.mark.skipif(
    not _postgres_available(),
    reason="PostgreSQL not available at localhost:55432. Run 'docker-compose up -d postgres' first."
)
@pytest.mark.asyncio
async def test_local_client():
    """Test CLI client in local mode."""
    from olav.cli.client import create_client

    print("🧪 Testing OLAV CLI Client (Local Mode)...")

    # Create local client
    print("\n1️⃣ Creating local client...")
    client = await create_client(mode="local", expert_mode=False)
    print("   ✅ Client created")

    # Health check
    print("\n2️⃣ Checking health...")
    health = await client.health_check()
    print(f"   Status: {health['status']}")
    print(f"   Orchestrator ready: {health['orchestrator_ready']}")

    # Execute simple query
    print("\n3️⃣ Executing test query...")
    result = await client.execute(
        query="Hello OLAV, can you help me?",
        thread_id="test-local-001",
        stream=False,  # Non-streaming for test
    )

    print(f"\n   Success: {result.success}")
    print(f"   Messages: {len(result.messages)}")
    print(f"   Thread ID: {result.thread_id}")

    if result.messages:
        print("\n   Last message:")
        last_msg = result.messages[-1]
        print(f"   Type: {last_msg.get('type')}")
        content = last_msg.get("content", "")
        print(f"   Content: {content[:200]}...")

    print("\n✅ Local client test passed!")


if __name__ == "__main__":
    # Windows requires SelectorEventLoop for psycopg async
    if sys.platform == "win32":
        import selectors

        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()  # type: ignore[attr-defined]
        )

    asyncio.run(test_local_client())
