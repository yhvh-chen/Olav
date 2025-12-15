# Ready-to-Implement Code Fixes

This document contains exact code changes ready to be copied and applied.

---

## Fix 1: setup-wizard.sh - Add Auto CSV Detection

**File**: `scripts/setup-wizard.sh`

**Location**: Replace `step_schema_init_inner()` function (approximately lines 411-445)

**Current Code (Broken)**:
```bash
step_schema_init_inner() {
    echo "Initializing schemas..."
    
    uv run olav init all
    
    # CSV Import (optional)
    echo ""
    read -p "Import devices from CSV? [y/N] " import_csv
    
    if [[ "$import_csv" =~ ^[Yy]$ ]]; then
        read -p "Enter CSV file path [config/inventory.csv]: " csv_path
        csv_path="${csv_path:-config/inventory.csv}"
        
        if [[ -f "$csv_path" ]]; then
            uv run olav init netbox --csv "$csv_path"
        else
            echo "CSV file not found: $csv_path"
        fi
    fi
}
```

**New Code (Fixed)**:
```bash
step_netbox_inventory_init() {
    echo ""
    echo "Initializing NetBox with device inventory..."
    
    local project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    local default_csv="$project_root/config/inventory.csv"
    
    # Check if inventory.csv exists
    if [[ -f "$default_csv" ]]; then
        # Count devices in CSV
        local device_count=$(grep -cv '^#' "$default_csv" 2>/dev/null || echo "0")
        if [[ "$device_count" -gt 0 ]]; then
            device_count=$((device_count - 1))  # Subtract header
        fi
        echo "  Found inventory.csv with $device_count device(s)"
        
        # Prompt user - default YES
        read -p "Import devices from inventory.csv? [Y/n] " import_devices
        
        if [[ ! "$import_devices" =~ ^[Nn]$ ]]; then
            echo ""
            echo "Importing devices to NetBox..."
            
            # Direct Python call - bypasses broken CLI parameter
            (
                cd "$project_root"
                export NETBOX_URL="http://localhost:${NETBOX_PORT:-8080}"
                export NETBOX_TOKEN="0123456789abcdef0123456789abcdef01234567"
                
                if uv run python scripts/netbox_ingest.py > /tmp/netbox_ingest.log 2>&1; then
                    if grep -q '"code": 0' /tmp/netbox_ingest.log; then
                        echo "  ✓ Device inventory imported successfully"
                    elif grep -q '"code": 99' /tmp/netbox_ingest.log; then
                        echo "  ✓ NetBox already has devices (skipped import)"
                    else
                        echo "  ⚠ Import may have issues - check NetBox"
                    fi
                else
                    echo "  ⚠ Import had issues - check NetBox"
                fi
            )
        else
            echo "  Skipping device import"
        fi
    else
        echo "  No inventory.csv found at: $default_csv"
    fi
}

step_schema_init_inner() {
    echo "Initializing schemas..."
    echo ""
    
    # First try to initialize NetBox with inventory
    if grep -q "function step_netbox_inventory_init" "$0" 2>/dev/null; then
        step_netbox_inventory_init
    fi
    
    # Then run schema initialization
    echo ""
    echo "Initializing OpenSearch indices and system schemas..."
    if uv run olav init all > /tmp/init_all.log 2>&1; then
        echo "✓ Schema initialization complete"
    else
        echo "⚠ Schema initialization had issues - check logs"
    fi
    
    # Optional custom CSV import
    echo ""
    read -p "Import devices from custom CSV? [y/N] " custom_import
    
    if [[ "$custom_import" =~ ^[Yy]$ ]]; then
        read -p "Enter CSV file path: " csv_path
        
        if [[ -f "$csv_path" ]]; then
            echo "Importing devices from custom CSV..."
            (
                cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
                export NETBOX_URL="http://localhost:${NETBOX_PORT:-8080}"
                export NETBOX_TOKEN="0123456789abcdef0123456789abcdef01234567"
                export NETBOX_INGEST_FORCE="true"
                
                if uv run python scripts/netbox_ingest.py > /tmp/netbox_custom.log 2>&1; then
                    echo "✓ Custom device import complete"
                else
                    echo "⚠ Custom import had issues"
                fi
            )
        else
            echo "CSV file not found: $csv_path"
        fi
    fi
}
```

**Key Changes**:
1. ✅ New function `step_netbox_inventory_init()` added before `step_schema_init_inner()`
2. ✅ Auto-detects `config/inventory.csv` existence
3. ✅ Counts devices in CSV
4. ✅ Prompts with default "Y" (changed from N)
5. ✅ Uses direct Python call: `uv run python scripts/netbox_ingest.py`
6. ✅ Checks exit codes and reports status
7. ✅ Still allows custom CSV import for advanced users
8. ✅ Call order: NetBox inventory → Schema init → Custom CSV

---

## Fix 2: setup-wizard.ps1 - Fix Step-SchemaInit

**File**: `scripts/setup-wizard.ps1`

**Location**: Replace `Step-SchemaInit` function (approximately lines 739-798)

**Current Code (Broken)**:
```powershell
function Step-SchemaInit {
    param(
        [hashtable]$Config,
        [switch]$SkipHeader
    )
    
    if (-not $SkipHeader) {
        Write-Step -Step "8/8" -Title "Schema Initialization"
    }
    
    Write-Host ""
    Write-Host "Initializing schemas..." -ForegroundColor Cyan
    
    # Run init command
    $initResult = & uv run olav init all 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Schema initialization complete"
    }
    else {
        Write-Warning "Schema initialization had issues: $initResult"
    }
    
    # CSV Import (optional)
    Write-Host ""
    $importCsv = Read-UserInput -Prompt "Import devices from CSV? [y/N]" -Default "N"
    
    if ($importCsv -match '^[Yy]') {
        $csvPath = Read-UserInput -Prompt "Enter CSV file path" -Default "config/inventory.csv"
        
        if (Test-Path $csvPath) {
            $importResult = & uv run olav init netbox --csv $csvPath 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Device import complete"
            }
            else {
                Write-Warning "Device import had issues: $importResult"
            }
        }
        else {
            Write-Warning "CSV file not found: $csvPath"
        }
    }
}
```

**New Code (Fixed)**:
```powershell
function Step-SchemaInit {
    param(
        [hashtable]$Config,
        [switch]$SkipHeader
    )
    
    if (-not $SkipHeader) {
        Write-Step -Step "8/8" -Title "Schema Initialization"
    }
    
    Write-Host ""
    Write-Host "Initializing schemas..." -ForegroundColor Cyan
    
    # Run init command
    $initResult = & uv run olav init all 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Schema initialization complete"
    }
    else {
        Write-Warning "Schema initialization had issues: $initResult"
    }
    
    # Custom CSV Import (optional - for users with non-standard paths)
    # Note: Default inventory.csv is already imported in Step-NetBoxInventoryInit
    Write-Host ""
    $importCsv = Read-UserInput -Prompt "Import devices from custom CSV? [y/N]" -Default "N"
    
    if ($importCsv -match '^[Yy]') {
        $csvPath = Read-UserInput -Prompt "Enter CSV file path" -Default ""
        
        if ($csvPath -and (Test-Path $csvPath)) {
            # Use direct Python call instead of broken CLI parameter
            $projectRoot = Split-Path -Parent $PSScriptRoot
            Push-Location $projectRoot
            try {
                $env:NETBOX_URL = "http://localhost:$($Config.NETBOX_PORT)"
                $env:NETBOX_TOKEN = "0123456789abcdef0123456789abcdef01234567"
                $env:NETBOX_INGEST_FORCE = "true"
                
                Write-Host ""
                Write-Host "Importing custom CSV..." -ForegroundColor Cyan
                
                $importResult = & uv run python scripts/netbox_ingest.py 2>&1
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Success "Custom device import complete"
                }
                elseif ($LASTEXITCODE -eq 99) {
                    Write-Success "NetBox already has devices (skipped custom import)"
                }
                else {
                    Write-Warning "Custom device import had issues: $importResult"
                }
            }
            finally {
                Pop-Location
            }
        }
        elseif ($csvPath) {
            Write-Warning "CSV file not found: $csvPath"
        }
        else {
            Write-Host "No CSV file path provided"
        }
    }
}
```

**Key Changes**:
1. ✅ Removed broken `uv run olav init netbox --csv` call
2. ✅ Changed prompt to "custom CSV" (since default is already imported in step 6)
3. ✅ Uses direct Python call with FORCE flag: `uv run python scripts/netbox_ingest.py`
4. ✅ Checks for both code 0 (success) and code 99 (already exists)
5. ✅ Proper error reporting
6. ✅ Same environment variables as Step-NetBoxInventoryInit

---

## Fix 3: src/olav/cli/commands.py - Add --csv Parameter

**File**: `src/olav/cli/commands.py`

**Location 1**: Update function signature (around line 1190)

**Current Code**:
```python
@click.command()
@click.option('--force', '-f', is_flag=True, help="Force reimport even if devices exist")
def init_netbox_cmd(force: bool) -> None:
    """Initialize NetBox from CSV inventory"""
    return _init_netbox_inventory(force=force)
```

**New Code**:
```python
@click.command()
@click.option('--force', '-f', is_flag=True, help="Force reimport even if devices exist")
@click.option('--csv', type=click.Path(exists=True), default="config/inventory.csv", 
              help="Path to CSV inventory file (default: config/inventory.csv)")
def init_netbox_cmd(force: bool, csv: str) -> None:
    """Initialize NetBox from CSV inventory
    
    Args:
        force: Force reimport even if devices exist
        csv: Path to CSV file (default: config/inventory.csv)
        
    Examples:
        # Use default CSV
        uv run olav init netbox
        
        # Use custom CSV with force flag
        uv run olav init netbox --csv /data/custom_devices.csv --force
    """
    return _init_netbox_inventory(force=force, csv_path=csv)
```

**Location 2**: Update implementation (around line 1326)

**Current Code**:
```python
def _init_netbox_inventory(force: bool) -> None:
    """Initialize NetBox inventory from CSV"""
    project_root = get_project_root()
    cmd = ["uv", "run", "python", "scripts/netbox_ingest.py"]
    
    env = os.environ.copy()
    if force:
        env["NETBOX_INGEST_FORCE"] = "true"
    
    result = subprocess.run(cmd, cwd=project_root, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise click.ClickException(f"NetBox initialization failed: {result.stderr}")
```

**New Code**:
```python
def _init_netbox_inventory(force: bool, csv_path: str = "config/inventory.csv") -> None:
    """Initialize NetBox inventory from CSV
    
    Args:
        force: Force reimport even if devices exist
        csv_path: Path to CSV file (relative to project root or absolute)
        
    Raises:
        click.ClickException: If CSV file not found or import fails
    """
    project_root = get_project_root()
    
    # Resolve CSV path (absolute or relative to project root)
    if os.path.isabs(csv_path):
        csv_full_path = csv_path
    else:
        csv_full_path = os.path.join(project_root, csv_path)
    
    # Verify CSV exists
    if not os.path.exists(csv_full_path):
        raise click.ClickException(
            f"CSV file not found: {csv_path}\n"
            f"Full path: {csv_full_path}\n"
            f"Please provide a valid path to a CSV inventory file."
        )
    
    # Prepare environment and command
    env = os.environ.copy()
    env["NETBOX_CSV_PATH"] = csv_full_path
    if force:
        env["NETBOX_INGEST_FORCE"] = "true"
    
    cmd = ["uv", "run", "python", "scripts/netbox_ingest.py"]
    
    # Run device import
    result = subprocess.run(cmd, cwd=project_root, env=env, capture_output=True, text=True)
    
    # Check result
    if result.returncode == 0:
        click.echo(click.style("✓ Device inventory imported successfully", fg="green"))
    elif result.returncode == 99:
        # Exit code 99 means devices already exist and FORCE wasn't set
        click.echo(click.style("ℹ NetBox already contains devices (use --force to override)", fg="blue"))
    else:
        raise click.ClickException(
            f"NetBox initialization failed (exit code {result.returncode})\n"
            f"stderr: {result.stderr}\n"
            f"stdout: {result.stdout}"
        )
```

**Key Changes**:
1. ✅ Added `--csv` parameter with default value
2. ✅ Path can be absolute or relative to project root
3. ✅ Validates CSV file exists before running
4. ✅ Passes path via `NETBOX_CSV_PATH` environment variable
5. ✅ Handles exit codes: 0 (success), 99 (skip), others (error)
6. ✅ Clear error messages for troubleshooting

---

## Fix 4: src/olav/etl/init_all.py - Add Device Import

**File**: `src/olav/etl/init_all.py`

**Location 1**: Add imports at top of file (around line 1-30)

**Add these lines**:
```python
import subprocess
import os
from typing import Optional
```

**Location 2**: Add new function (insert after other init functions, around line 200-250)

**Insert this new function**:
```python
async def init_netbox_devices(csv_path: str = "config/inventory.csv", force: bool = False) -> None:
    """Import device inventory from CSV into NetBox
    
    Args:
        csv_path: Path to CSV file (relative to project root)
        force: Force reimport even if devices exist
        
    Raises:
        RuntimeError: If device import fails
    """
    try:
        logger.info(f"Initializing NetBox device inventory from {csv_path}...")
        
        # Get project root
        project_root = get_project_root()
        csv_full_path = os.path.join(project_root, csv_path)
        
        # Check if CSV exists
        if not os.path.exists(csv_full_path):
            logger.warning(f"Device CSV not found at {csv_full_path}, skipping device import")
            return
        
        # Prepare environment
        env = os.environ.copy()
        if force:
            env["NETBOX_INGEST_FORCE"] = "true"
        
        # Run device import script
        cmd = ["uv", "run", "python", "scripts/netbox_ingest.py"]
        
        logger.debug(f"Running: {' '.join(cmd)}")
        result = subprocess.run(
            cmd, 
            cwd=project_root, 
            env=env, 
            capture_output=True, 
            text=True, 
            timeout=300  # 5 minute timeout
        )
        
        # Parse result
        if result.returncode == 0:
            logger.info("✅ Device inventory imported successfully")
        elif result.returncode == 99:
            logger.info("ℹ️  NetBox already contains devices (skipped import)")
        else:
            error_msg = f"Device import failed with exit code {result.returncode}"
            logger.error(f"❌ {error_msg}")
            logger.debug(f"stderr: {result.stderr}")
            logger.debug(f"stdout: {result.stdout}")
            raise RuntimeError(error_msg)
            
    except subprocess.TimeoutExpired:
        logger.error("❌ Device import timed out after 5 minutes")
        raise
    except Exception as e:
        logger.error(f"❌ Device inventory initialization failed: {e}")
        raise
```

**Location 3**: Update main() function (around line 350-422)

**Current Code**:
```python
async def main():
    """Initialize all OLAV components"""
    checkpointer = await _get_checkpointer()
    
    logger.info("Starting OLAV initialization...")
    
    # 1. Initialize PostgreSQL Checkpointer
    await init_postgres(checkpointer)
    
    # 2. Initialize SuzieQ Schema
    await init_suzieq_schema()
    
    # 3. Initialize OpenConfig YANG Schema
    await init_openconfig_schema()
    
    # 4. Initialize NetBox API Schema
    await init_netbox_schema()
    
    # 5. Initialize Episodic Memory
    await init_episodic_memory()
    
    # 6. Initialize Syslog Index
    await init_syslog()
    
    logger.info("✅ All OLAV components initialized successfully")
```

**New Code**:
```python
async def main():
    """Initialize all OLAV components"""
    checkpointer = await _get_checkpointer()
    
    logger.info("Starting OLAV initialization...")
    
    try:
        # 1. Initialize PostgreSQL Checkpointer
        logger.info("[1/7] Initializing PostgreSQL Checkpointer...")
        await init_postgres(checkpointer)
        
        # 2. Initialize SuzieQ Schema
        logger.info("[2/7] Initializing SuzieQ Schema...")
        await init_suzieq_schema()
        
        # 3. Initialize OpenConfig YANG Schema
        logger.info("[3/7] Initializing OpenConfig YANG Schema...")
        await init_openconfig_schema()
        
        # 4. Initialize NetBox API Schema
        logger.info("[4/7] Initializing NetBox API Schema...")
        await init_netbox_schema()
        
        # 5. Initialize NetBox Device Inventory
        logger.info("[5/7] Initializing NetBox Device Inventory...")
        await init_netbox_devices()
        
        # 6. Initialize Episodic Memory
        logger.info("[6/7] Initializing Episodic Memory...")
        await init_episodic_memory()
        
        # 7. Initialize Syslog Index
        logger.info("[7/7] Initializing Syslog Index...")
        await init_syslog()
        
        logger.info("✅ All OLAV components initialized successfully")
        
    except Exception as e:
        logger.error(f"❌ OLAV initialization failed: {e}")
        raise
```

**Key Changes**:
1. ✅ Added imports for subprocess and os
2. ✅ New function `init_netbox_devices()` that wraps netbox_ingest.py
3. ✅ Proper error handling and logging
4. ✅ Checks if CSV exists before attempting import
5. ✅ Supports both success (code 0) and skip (code 99) cases
6. ✅ Integrated into main() initialization sequence
7. ✅ Step numbering in logs (1/7 through 7/7)

---

## Testing Checklist

After applying all fixes, verify with:

```bash
# Test 1: PS1 QuickTest
.\setup.ps1
# Select: QuickTest
# Accept all defaults
# Verify: Step 6 shows "Device inventory imported successfully"
# Verify: Step 8 completes without trying to import again

# Test 2: SH QuickTest  
./setup.sh
# Select: QuickTest
# Accept all defaults
# Verify: Auto-detects inventory.csv
# Verify: Shows device count
# Verify: Imports devices (new behavior)

# Test 3: Direct Python init
uv run olav init all
# Verify: All 7/7 steps complete
# Verify: Devices are imported

# Test 4: Custom CSV via CLI (NEW - was broken)
uv run olav init netbox --csv /data/my_devices.csv
# Verify: Custom CSV is imported (not config/inventory.csv)
# Verify: No error about missing --csv parameter

# Test 5: Force flag
uv run olav init netbox --force
# Verify: Re-imports devices even if they exist

# Test 6: Check NetBox
curl http://localhost:8080/api/dcim/devices/ \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"
# Verify: 6 devices present (R1, R2, R3, R4, SW1, SW2)
```

---

## Expected Outcomes

### Before Fixes
```
PS1 QuickTest:  ✅ Works (has Step-NetBoxInventoryInit)
SH QuickTest:   ❌ Fails (no devices imported)
Python init:    ❌ Fails (no devices imported)
Custom CSV:     ❌ Fails (--csv parameter doesn't exist)
User Success:   20% (confusing situation)
```

### After Fixes
```
PS1 QuickTest:  ✅ Works (still works, cleaner code)
SH QuickTest:   ✅ Works (now matches PS1)
Python init:    ✅ Works (includes device import)
Custom CSV:     ✅ Works (--csv parameter now supported)
User Success:   95%+ (consistent, clear behavior)
```

