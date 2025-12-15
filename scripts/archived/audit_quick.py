#!/usr/bin/env python3
"""Quick audit of unused code - simplified version.

This script identifies:
1. Python files in config/ and src/olav/ not imported anywhere
2. Uses vulture for dead code detection

Usage:
    uv run python scripts/audit_quick.py
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "olav"
CONFIG_DIR = PROJECT_ROOT / "config"


def get_all_imports() -> set[str]:
    """Get all imported module names using grep."""
    imports = set()
    
    # Search for import statements
    result = subprocess.run(
        ["git", "grep", "-h", "-E", r"^(from|import)\s+"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT
    )
    
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("from "):
            # from X import Y
            parts = line.split()
            if len(parts) >= 2:
                module = parts[1]
                imports.add(module)
                # Add all parent modules
                module_parts = module.split(".")
                for i in range(len(module_parts)):
                    imports.add(".".join(module_parts[:i+1]))
        elif line.startswith("import "):
            # import X, Y, Z
            parts = line[7:].split(",")
            for part in parts:
                module = part.strip().split()[0]  # Handle 'import X as Y'
                imports.add(module)
                module_parts = module.split(".")
                for i in range(len(module_parts)):
                    imports.add(".".join(module_parts[:i+1]))
    
    return imports


def file_to_module(filepath: Path) -> str:
    """Convert a file path to a module path."""
    if filepath.is_relative_to(SRC_DIR.parent):
        rel = filepath.relative_to(SRC_DIR.parent)
    else:
        rel = filepath.relative_to(PROJECT_ROOT)
    return str(rel.with_suffix("")).replace("/", ".").replace("\\", ".")


def find_unused_files() -> list[tuple[Path, str]]:
    """Find Python files that are never imported."""
    unused = []
    imports = get_all_imports()
    
    # Check config/ files
    for f in CONFIG_DIR.glob("*.py"):
        if f.name in ("__init__.py", "__main__.py", "__pycache__"):
            continue
        module = f"config.{f.stem}"
        if module not in imports and f.stem not in imports:
            unused.append((f, module))
    
    # Check src/olav/ files recursively
    for f in SRC_DIR.rglob("*.py"):
        if f.name in ("__init__.py", "__main__.py") or "__pycache__" in str(f):
            continue
        module = file_to_module(f)
        
        # Check if any variation is imported
        found = False
        parts = module.split(".")
        for i in range(len(parts)):
            check = ".".join(parts[i:])
            if check in imports:
                found = True
                break
        
        if not found:
            unused.append((f, module))
    
    return unused


def run_vulture() -> str:
    """Run vulture to find dead code."""
    result = subprocess.run(
        ["uv", "run", "vulture", "src/olav", "config", "--min-confidence", "80"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=60
    )
    return result.stdout + result.stderr


def main():
    print("=" * 60)
    print("OLAV Code Audit Report")
    print("=" * 60)
    print()
    
    # 1. Find unused files
    print("## 1. Potentially Unused Files")
    print("-" * 40)
    unused_files = find_unused_files()
    
    if unused_files:
        for filepath, module in unused_files:
            rel_path = filepath.relative_to(PROJECT_ROOT)
            print(f"  - {rel_path} ({module})")
    else:
        print("  No unused files found.")
    print()
    
    # 2. Run vulture for dead code
    print("## 2. Dead Code Detection (vulture)")
    print("-" * 40)
    try:
        vulture_output = run_vulture()
        if vulture_output.strip():
            # Filter out known false positives
            lines = vulture_output.strip().splitlines()
            filtered = []
            for line in lines:
                # Skip known patterns
                if any(skip in line for skip in [
                    "unused import",  # Often used for re-export
                    "__init__.py",    # Re-exports
                    "unused variable 'e'",  # Exception handling
                    "unused variable '_'",  # Intentional ignore
                ]):
                    continue
                filtered.append(line)
            
            if filtered:
                for line in filtered[:30]:  # Limit output
                    print(f"  {line}")
                if len(filtered) > 30:
                    print(f"  ... and {len(filtered) - 30} more")
            else:
                print("  No significant dead code found.")
        else:
            print("  No dead code found.")
    except subprocess.TimeoutExpired:
        print("  Vulture timed out after 60s")
    except FileNotFoundError:
        print("  Vulture not installed. Run: uv add --dev vulture")
    print()
    
    # 3. Check for common dead code patterns
    print("## 3. Ghost Code Patterns")
    print("-" * 40)
    
    # Look for TODO/FIXME/XXX/HACK comments
    result = subprocess.run(
        ["git", "grep", "-n", "-E", r"(TODO|FIXME|XXX|HACK|DEPRECATED):?"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT
    )
    
    todos = []
    for line in result.stdout.splitlines():
        if not line.startswith("archive/") and not line.startswith("docs/archive/"):
            todos.append(line)
    
    if todos:
        print(f"  Found {len(todos)} TODO/FIXME comments:")
        for line in todos[:15]:
            print(f"    {line[:100]}")
        if len(todos) > 15:
            print(f"    ... and {len(todos) - 15} more")
    else:
        print("  No TODO/FIXME comments found.")
    print()
    
    # 4. Check for commented-out code blocks
    print("## 4. Commented-out Code Blocks")
    print("-" * 40)
    result = subprocess.run(
        ["git", "grep", "-n", "-E", r"^#\s*(def |class |import |from )"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT
    )
    
    commented = []
    for line in result.stdout.splitlines():
        if not line.startswith("archive/") and not line.startswith("docs/"):
            commented.append(line)
    
    if commented:
        print(f"  Found {len(commented)} commented-out code lines:")
        for line in commented[:10]:
            print(f"    {line[:100]}")
        if len(commented) > 10:
            print(f"    ... and {len(commented) - 10} more")
    else:
        print("  No commented-out code found.")
    print()
    
    print("=" * 60)
    print("Audit Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
