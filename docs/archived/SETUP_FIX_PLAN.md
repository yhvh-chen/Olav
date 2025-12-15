# OLAV Setup Initialization: Immediate Action Plan

## Problem Summary

The OLAV initialization system has a **critical architectural gap**: device inventory import is disconnected from the main initialization flow.

**Current Symptoms:**
- ✅ Infrastructure initializes (PostgreSQL, OpenSearch) - ALL GOOD
- ✅ Schemas initialize (SuzieQ, OpenConfig, NetBox APIs) - ALL GOOD  
- ❌ **Device inventory is skipped entirely** - CRITICAL ISSUE
- Users get success message but system is non-functional (empty NetBox)

**Root Causes:**
1. `init_all.py` doesn't call device import
2. `setup-wizard.sh` missing auto CSV detection
3. `setup-wizard.ps1` tries to use non-existent `--csv` CLI parameter
4. `olav init netbox --csv <path>` parameter isn't implemented

---

## Action Items

### PRIORITY 1: Fix setup-wizard.sh (Cross-platform consistency)

**File**: `scripts/setup-wizard.sh`

**Problem**: Missing automatic device CSV detection. Users must manually opt-in to device import, with default being "No".

**Fix**: Add auto-detection logic from PS1 (20 lines) to line ~410

**Before (Lines 411-445)**:
```bash
step_schema_init_inner() {
    echo "Initializing schemas..."
    
    # Just run init all
    uv run olav init all
    
    # Optional CSV import (default NO)
    read -p "Import devices from CSV? [y/N] " import_csv
    if [[ "$import_csv" =~ ^[Yy]$ ]]; then
        read -p "Enter CSV file path [config/inventory.csv]: " csv_path
        csv_path="${csv_path:-config/inventory.csv}"
        uv run olav init netbox --csv "$csv_path"
    fi
}
```

**After**:
```bash
step_schema_init_inner() {
    echo "Initializing schemas..."
    
    # Auto-detect inventory.csv and import with direct Python call
    csv_file="config/inventory.csv"
    if [[ -f "$csv_file" ]]; then
        device_count=$(grep -cv '^#' "$csv_file" | tail -1)
        echo "  Found inventory.csv with $device_count device(s)"
        
        # Prompt with default YES
        read -p "Import devices from inventory.csv? [Y/n] " import_csv
        if [[ ! "$import_csv" =~ ^[Nn]$ ]]; then
            echo "Importing devices to NetBox..."
            
            # Direct Python call (bypasses broken CLI parameter)
            export NETBOX_URL="http://localhost:${NETBOX_PORT:-8080}"
            export NETBOX_TOKEN="0123456789abcdef0123456789abcdef01234567"
            
            uv run python scripts/netbox_ingest.py
            
            if [[ $? -eq 0 ]]; then
                echo "✓ Device inventory imported successfully"
            elif [[ $? -eq 99 ]]; then
                echo "✓ NetBox already has devices (skipped import)"
            else
                echo "⚠ Import had issues - check NetBox"
            fi
        else
            echo "  Skipping device import"
        fi
    else
        echo "  No inventory.csv found"
    fi
    
    # Run schema init
    uv run olav init all
    
    # Optional: Allow manual CSV import from custom path
    read -p "Import devices from custom CSV? [y/N] " custom_import
    if [[ "$custom_import" =~ ^[Yy]$ ]]; then
        read -p "Enter CSV file path: " csv_path
        if [[ -f "$csv_path" ]]; then
            export NETBOX_URL="http://localhost:${NETBOX_PORT:-8080}"
            export NETBOX_TOKEN="0123456789abcdef0123456789abcdef01234567"
            NETBOX_INGEST_FORCE=true uv run python scripts/netbox_ingest.py
        else
            echo "CSV file not found: $csv_path"
        fi
    fi
}
```

**Expected Result**: SH script now behaves identically to PS1 (auto-detect + direct call + optional custom).

---

### PRIORITY 2: Fix setup-wizard.ps1 Step-SchemaInit (Remove broken CLI call)

**File**: `scripts/setup-wizard.ps1`

**Problem**: Lines 761-780 call `uv run olav init netbox --csv` which doesn't exist.

**Before (Lines 761-780)**:
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

**After** (Remove broken CLI call, use direct Python):
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
                
                $importResult = & uv run python scripts/netbox_ingest.py 2>&1
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Success "Device import complete"
                }
                else {
                    Write-Warning "Device import had issues: $importResult"
                }
            }
            finally {
                Pop-Location
            }
        }
        else {
            Write-Warning "CSV file not found or path not provided"
        }
    }
}
```

**Expected Result**: PS1 script stops trying to use non-existent CLI parameter, uses proven direct Python approach instead.

---

### PRIORITY 3: Add --csv parameter to CLI (Optional custom paths)

**File**: `src/olav/cli/commands.py`

**Problem**: Shell scripts call `olav init netbox --csv <path>` but parameter isn't implemented.

**Location 1 - Function signature (Line ~1190)**:

**Before**:
```python
@click.command()
@click.option('--force', '-f', is_flag=True, help="Force reimport even if devices exist")
def init_netbox_cmd(force: bool) -> None:
    """Initialize NetBox from CSV inventory"""
    return _init_netbox_inventory(force=force)
```

**After**:
```python
@click.command()
@click.option('--force', '-f', is_flag=True, help="Force reimport even if devices exist")
@click.option('--csv', type=click.Path(exists=True), default="config/inventory.csv", 
              help="Path to CSV inventory file")
def init_netbox_cmd(force: bool, csv: str) -> None:
    """Initialize NetBox from CSV inventory
    
    Args:
        force: Force reimport even if devices exist
        csv: Path to CSV file (default: config/inventory.csv)
    """
    return _init_netbox_inventory(force=force, csv_path=csv)
```

**Location 2 - Implementation (Line ~1326)**:

**Before**:
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

**After**:
```python
def _init_netbox_inventory(force: bool, csv_path: str = "config/inventory.csv") -> None:
    """Initialize NetBox inventory from CSV"""
    project_root = get_project_root()
    csv_full_path = os.path.join(project_root, csv_path)
    
    # Verify CSV exists
    if not os.path.exists(csv_full_path):
        raise click.ClickException(f"CSV file not found: {csv_path}")
    
    # Set environment variable for netbox_ingest.py to read custom path
    env = os.environ.copy()
    env["NETBOX_CSV_PATH"] = csv_full_path
    if force:
        env["NETBOX_INGEST_FORCE"] = "true"
    
    cmd = ["uv", "run", "python", "scripts/netbox_ingest.py"]
    result = subprocess.run(cmd, cwd=project_root, env=env, capture_output=True, text=True)
    
    if result.returncode not in [0, 99]:  # 99 = already exists
        raise click.ClickException(f"NetBox initialization failed: {result.stderr}")
```

**Location 3 - Update netbox_ingest.py to read from env var (Line ~50)**:

**Before**:
```python
def main():
    rows = parse_csv("config/inventory.csv")  # Hardcoded path
```

**After**:
```python
def main():
    csv_path = os.getenv("NETBOX_CSV_PATH", "config/inventory.csv")
    rows = parse_csv(csv_path)
```

**Expected Result**: `olav init netbox --csv /data/custom.csv` now works properly, custom paths are respected.

---

### PRIORITY 4: Integrate device import into init_all.py (Python path consistency)

**File**: `src/olav/etl/init_all.py`

**Problem**: `uv run olav init all` initializes infrastructure and schemas but skips device import entirely.

**Before (Main function, lines ~350-422)**:
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

**After** (Add device import):
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
    
    # 5. Initialize NetBox Device Inventory
    await init_netbox_devices()  # NEW LINE
    
    # 6. Initialize Episodic Memory
    await init_episodic_memory()
    
    # 7. Initialize Syslog Index
    await init_syslog()
    
    logger.info("✅ All OLAV components initialized successfully")
```

**Add new function** (after line ~200):
```python
async def init_netbox_devices() -> None:
    """Import device inventory from CSV into NetBox"""
    try:
        logger.info("Initializing NetBox device inventory...")
        
        # Check if CSV exists
        project_root = get_project_root()
        csv_path = os.path.join(project_root, "config/inventory.csv")
        
        if not os.path.exists(csv_path):
            logger.warning(f"Device CSV not found at {csv_path}, skipping device import")
            return
        
        # Run device import script
        cmd = ["uv", "run", "python", "scripts/netbox_ingest.py"]
        env = os.environ.copy()
        
        result = subprocess.run(cmd, cwd=project_root, env=env, 
                              capture_output=True, text=True, timeout=300)
        
        # Exit codes: 0=success, 99=already exists, others=error
        if result.returncode == 0:
            logger.info("✅ Device inventory imported successfully")
        elif result.returncode == 99:
            logger.info("ℹ️  NetBox already contains devices (skipped import)")
        else:
            logger.error(f"Device import failed: {result.stderr}")
            raise RuntimeError(f"Device import failed with code {result.returncode}")
            
    except Exception as e:
        logger.error(f"❌ Device inventory initialization failed: {e}")
        raise
```

**Add import** (at top of file):
```python
import subprocess
import os
```

**Expected Result**: Running `uv run olav init all` now initializes devices along with infrastructure, providing complete working system.

---

## Implementation Order

1. **Do Priority 1 & 2 first** (Shell script fixes) - Quick wins, no dependencies
   - Time: ~30 minutes
   - Impact: Cross-platform consistency, working auto-detection
   - Risk: Low (adding code, not modifying existing)

2. **Do Priority 3** (CLI parameter) - Enables custom paths
   - Time: ~20 minutes
   - Impact: Users can import from non-standard locations
   - Risk: Low (CLI refactor is straightforward)

3. **Do Priority 4** (init_all.py) - Complete Python path
   - Time: ~20 minutes
   - Impact: Single command initialization
   - Risk: Low (new function, no breaking changes)

**Total Time**: ~70 minutes for complete fix

---

## Testing Checklist After Fixes

### Windows QuickTest (setup.ps1)
```powershell
.\setup.ps1
# Select QuickTest
# Accept all defaults
# Verify: devices imported automatically
# Status: Should see "✓ Device inventory imported successfully"
```

### Linux QuickTest (setup.sh)
```bash
./setup.sh
# Select QuickTest
# Accept all defaults
# Verify: devices imported automatically
# Status: Should see "✓ Device inventory imported successfully"
```

### Custom CSV Path (both)
```powershell
.\setup.ps1
# Select Production
# At Step-SchemaInit: Answer Y to custom CSV import
# Enter: /data/custom_devices.csv
# Verify: Correct file is imported (not config/inventory.csv)
```

### Direct Python Init (Linux)
```bash
# Modify config/inventory.csv
uv run olav init all
# Verify: Devices imported automatically
# Status: Should complete without errors
```

### Custom CSV via CLI (Linux)
```bash
uv run olav init netbox --csv /path/to/custom.csv
# Verify: Custom file is imported
# Status: Should succeed with exit code 0
```

---

## Expected Outcomes After Fixes

| Scenario | Before | After |
|----------|--------|-------|
| PS1 QuickTest with CSV | ✅ Works | ✅ Still works + fixed schema step |
| SH QuickTest with CSV | ❌ No devices | ✅ Auto-imports devices |
| Custom CSV import | ❌ Silently ignored | ✅ Works correctly |
| Python init_all.py | ❌ No devices | ✅ Imports devices |
| User confusion | HIGH | LOW |
| System functionality | 40% (no devices) | 100% (complete) |

---

## Documentation Updates Needed

**Update README.md:**
- Primary entry points: `./setup.ps1` (Windows) and `./setup.sh` (Linux)
- Both now automatically import devices from config/inventory.csv
- Optional custom CSV import available during setup

**Update QUICKSTART.md:**
- Clarify that device import is automatic in QuickTest mode
- Show that `uv run olav init all` now includes device import
- Document `--csv` parameter for CLI: `uv run olav init netbox --csv /path/to/devices.csv`

---

## Risk Assessment

**Risk Level: LOW**

- Changes are additions/refactors, not modifications to existing logic
- Direct Python calls are proven to work (already in PS1)
- Subprocess calls follow existing patterns in codebase
- Exit code handling matches netbox_ingest.py specifications
- No breaking changes to existing APIs

**Mitigation**:
- Test each priority sequentially
- Verify exit codes from netbox_ingest.py
- Check environment variable passing in all shells

