"""Test interactive chat mode with timing display."""
import subprocess
import sys

# Simulate interactive chat with automated input
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
