# JWT_SECRET_KEY Missing from .env - Root Cause Analysis

## Problem Statement
✅ **CONFIRMED**: Current `.env` file is missing `JWT_SECRET_KEY` required for server token generation.

## Root Cause
The issue is in `setup.ps1` function design:

| Component | QuickTest Mode | Production Mode |
|-----------|---|---|
| **Token Generation** | ✅ Called (line 1570) | ✅ Called (line 1570) |
| **Config.JWT_SECRET_KEY Set** | ✅ Yes | ✅ Yes |
| **.env Generation Function** | `Generate-EnvFile` (line 1072) | `Generate-EnvFile-Production` (line 1267) |
| **JWT_SECRET_KEY in .env** | ❌ **NOT INCLUDED** | ✅ Included (line 1344) |

### Code Analysis

**Problem Location 1: `Generate-EnvFile` function (QuickTest mode)**
```powershell
# Lines 1072-1145
function Generate-EnvFile {
    # ... includes many fields ...
    # BUT MISSING:
    # "JWT_SECRET_KEY=$($Config.JWT_SECRET_KEY)"
    
    # Ends without JWT_SECRET_KEY
    return $envLines -join "`n"
}
```

**Working Location 2: `Generate-EnvFile-Production` function (Production mode)**
```powershell
# Lines 1267-1360
function Generate-EnvFile-Production {
    # ... includes many fields ...
    # Line 1344 CORRECTLY includes:
    "JWT_SECRET_KEY=$($Config.JWT_SECRET_KEY)"
    # ... 
    return $envLines -join "`n"
}
```

## Current .env File Status

Generated using: `Generate-EnvFile` function (QuickTest mode)
- Contains: LLM_API_KEY, NETBOX_TOKEN, NETBOX_SECRET_KEY
- **Missing**: JWT_SECRET_KEY ❌
- Generated: 2025-12-10 20:13:17

## Solution

### Option 1: Add JWT_SECRET_KEY to Current .env (Quick Fix)

Add this line to `.env`:
```bash
# JWT Configuration
JWT_SECRET_KEY=<generate-new-random-base64>
```

To generate a 32-byte base64 value:
```powershell
# PowerShell
[System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))

# Linux/Mac
openssl rand -base64 32
```

Example:
```
JWT_SECRET_KEY=aB3xCd9eF2gHiJk1LmN4oPqRsT6uVwXyZ8aB0cDeFgHi==
```

### Option 2: Fix setup.ps1 Permanently (Recommended)

**Location**: `setup.ps1`, lines 1072-1145 in `Generate-EnvFile` function

**Change**:
```powershell
# Current (incorrect): Missing JWT_SECRET_KEY
$envLines += @(
    ""
    "# Port Configuration"
    "OPENSEARCH_PORT=$($Config.OPENSEARCH_PORT)"
    "POSTGRES_PORT=$($Config.POSTGRES_PORT)"
    "NETBOX_PORT=$($Config.NETBOX_PORT)"
)

# Fixed: Add JWT_SECRET_KEY before port configuration
$envLines += @(
    ""
    "# JWT Configuration"
    "JWT_SECRET_KEY=$($Config.JWT_SECRET_KEY)"
    ""
    "# Port Configuration"
    "OPENSEARCH_PORT=$($Config.OPENSEARCH_PORT)"
    "POSTGRES_PORT=$($Config.POSTGRES_PORT)"
    "NETBOX_PORT=$($Config.NETBOX_PORT)"
)
```

**File**: `setup.ps1`
**Function**: `Generate-EnvFile`
**Lines**: Around 1138-1145
**Action**: Add JWT configuration section before Port Configuration section

### Option 3: Merge Both Functions

Consolidate `Generate-EnvFile` and `Generate-EnvFile-Production` into a single function that handles both modes (DRY principle).

## Why This Matters

**JWT_SECRET_KEY is CRITICAL for**:
- ✅ Server-side token validation
- ✅ Client registration token issuance
- ✅ Bearer token verification on API requests
- ❌ Without it: Server cannot validate any tokens → authentication fails

## Timeline

1. **setup.ps1 execution**: `Step-TokenGeneration` generates `$Config.JWT_SECRET_KEY` ✅
2. **setup.ps1 execution**: `Show-Completion` says "Configuration saved to: .env" ✅
3. **Actual .env generation**: `Generate-EnvFile` called with $Config but **omits JWT_SECRET_KEY** ❌
4. **Result**: `.env` has no JWT_SECRET_KEY ❌

## Testing After Fix

```bash
# Verify JWT_SECRET_KEY is in .env
cat .env | grep JWT_SECRET_KEY

# Expected output:
# JWT_SECRET_KEY=aB3xCd9eF2gHiJk1LmN4oPqRsT6uVwXyZ8aB0cDeFgHi==
```

## Implementation Priority
🔴 **CRITICAL** - Fix immediately as this breaks all token-based authentication
- **Quick Fix (5 min)**: Option 1 - manually add to .env
- **Permanent Fix (10 min)**: Option 2 - update setup.ps1
- **Best Fix (20 min)**: Option 3 - merge both .env generation functions

## Files That Need JWT_SECRET_KEY

1. **.env** - Server configuration
   - Used by: server startup, JWT library initialization
   - Format: `JWT_SECRET_KEY=<base64-32-bytes>`

2. **Server Code** (likely)
   - Location: `src/olav/server/api/auth.py` or similar
   - Usage: `jwt.encode(..., key=os.getenv("JWT_SECRET_KEY"))`
   - Status: ✅ Probably already implements this correctly

3. **CLI Code** (optional for client-side)
   - Location: `src/olav/cli/auth.py`
   - Usage: Only validates tokens from server
   - Status: ✅ No JWT_SECRET_KEY needed on client
