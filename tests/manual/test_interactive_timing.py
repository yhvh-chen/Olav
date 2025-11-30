"""
Test interactive chat mode with timing display.

This is a manual test that requires infrastructure and human interaction.
Run directly with: python tests/manual/test_interactive_timing.py
"""
import subprocess
import sys

import pytest


# Skip when imported by pytest - this is a manual script
pytestmark = pytest.mark.skip(reason="Manual test - run directly with 'python tests/manual/test_interactive_timing.py'")


def test_interactive_timing():
    """Placeholder test that explains how to run this manual test."""
    pass


if __name__ == "__main__":
    # Only run when executed directly, not when imported
    chat_input = """查询BGP状态
exit
"""

    proc = subprocess.Popen(
        [sys.executable, "-m", "olav.main", "chat"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=r"C:\Users\yhvh\Documents\code\Olav",
    )

    output, _ = proc.communicate(input=chat_input, timeout=120)

    # Check for timing table in output
    if "⏱️  工具执行耗时" in output:
        print("✅ Timing table found in output!")
        # Extract timing section
        lines = output.split("\n")
        in_timing = False
        for line in lines:
            if "⏱️  工具执行耗时" in line:
                in_timing = True
            if in_timing:
                print(line)
                if "总计" in line:
                    break
    else:
        print("❌ Timing table NOT found")
        print("\n--- Full Output ---")
        print(output[-1000:])  # Last 1000 chars
