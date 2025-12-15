# Token Generation & Authentication Flow Investigation

## Overview
The OLAV project implements a **two-tier token system** for authentication:
1. **Master Token** (server-side, one-time setup) - generated during initialization
2. **Session Token** (client-side, per-client) - generated after registration

## Token Generation & Storage Architecture

### Tier 1: Master Token (Server-Side Setup)

**Generation Source**: `setup.ps1` - `Step-TokenGeneration` function (lines 1226-1239)

```powershell
function Step-TokenGeneration {
    Write-Host "Generating JWT_SECRET_KEY..." -ForegroundColor Cyan
    
    # Generate 32-byte random value
    $Config.JWT_SECRET_KEY = [System.Convert]::ToBase64String(
        [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
    )
    Write-Host "JWT_SECRET_KEY generated: $($Config.JWT_SECRET_KEY.Substring(0, 20))..."
}
```

**Storage Location**: `.env` file (line 1339 in setup.ps1)
```powershell
JWT_SECRET_KEY=$($Config.JWT_SECRET_KEY)
```

**Purpose**: 
- Server-side signing key for JWT token creation
- Used by server to sign and validate all tokens
- Never shared with clients

**Current Status**: ⚠️ JWT_SECRET_KEY present in setup.ps1 but **not appearing in current `.env`** file
- Expected location: `.env` line with `JWT_SECRET_KEY=<base64-value>`
- Actual status: Only `NETBOX_TOKEN` and `NETBOX_SECRET_KEY` present
- **Issue**: Either script didn't complete or .env needs refresh

---

### Tier 2: Session Token (Client-Side Registration)

**Generation Flow**:

```
┌─────────────┐          ┌──────────────┐          ┌──────────────┐
│   CLI User  │          │  OLAV Server │          │  ~/.olav/    │
│  (setup.ps1)│          │              │          │  credentials │
└─────┬───────┘          └──────────────┘          └──────────────┘
      │                         │                         │
      │ 1. Register command     │                         │
      │    (master_token)       │                         │
      └────────────────────────>│                         │
      │                         │                         │
      │                    2. Validate master_token       │
      │                    3. Create session_token (JWT)  │
      │                    4. Return {session_token,      │
      │                         client_id, expires_at}    │
      │<────────────────────────┘                         │
      │                                                    │
      │ 5. Save credentials (--save flag)                 │
      ├───────────────────────────────────────────────────>
      │    OLAV_SESSION_TOKEN=<token>
      │    OLAV_CLIENT_ID=<id>
      │    OLAV_CLIENT_NAME=<name>
```

**Command**: `olav register --name "my-client" --token "master-token"`

**Source Code**: 
- Command handler: `src/olav/cli/commands.py` lines 675-730
- Client implementation: `src/olav/cli/thin_client.py` lines 298-327
- Credentials storage: `src/olav/cli/commands.py` lines 750-785

**Key Components**:

1. **Register Endpoint** (server): `POST /auth/register`
   - Expected payload: `{client_name, master_token}`
   - Returns: `{session_token, client_id, client_name, expires_at}`
   - Status: ✅ Implemented in thin_client.py but **server endpoint needs verification**

2. **Credentials Storage** (client): `~/.olav/credentials`
   - Format: Key=Value (INI-style)
   - Permissions: 0600 (Unix: user-only read/write)
   - Contents:
     ```
     OLAV_SESSION_TOKEN=<jwt-token>
     OLAV_CLIENT_ID=<unique-id>
     OLAV_CLIENT_NAME=<client-name>
     ```
   - Status: ✅ Fully implemented

---

## CLI Token Usage Flow

### Priority for Token Resolution

**Location**: `src/olav/cli/commands.py` lines 78-116

```python
def _get_config_from_env(server_url: str | None) -> tuple[ClientConfig, str | None]:
    """
    Token lookup priority:
    1. OLAV_API_TOKEN environment variable
    2. OLAV_API_TOKEN from .env file
    3. OLAV_SESSION_TOKEN from ~/.olav/credentials (session token from register)
    """
```

**Resolution Order**:
1. `$env:OLAV_API_TOKEN` (environment variable, highest priority)
2. `OLAV_API_TOKEN` from `.env` file
3. `OLAV_SESSION_TOKEN` from `~/.olav/credentials` (lowest priority)

**Usage**: Token passed to `OlavThinClient(config, auth_token=token)`

---

## Request Headers & Authentication

**Bearer Token Implementation**: `src/olav/cli/thin_client.py` lines 250-270

```python
def __init__(
    self,
    config: ClientConfig,
    auth_token: str | None = None,
):
    self.auth_token = auth_token
    ...

async def _build_headers(self) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if self.auth_token:
        headers["Authorization"] = f"Bearer {self.auth_token}"
    return headers
```

**All Requests Include**: `Authorization: Bearer {session_token}`

---

## Complete Token Flow Example

### Scenario: First-time Client Registration

```bash
# 1. User runs registration command (with master token from server startup)
olav register --name "alice-laptop" --token "abc123xyz...server-master-token"

# 2. CLI executes: src/olav/cli/commands.py::_register_client()
# 3. Creates HTTP connection to server
# 4. Posts to /auth/register with {client_name, master_token}
# 5. Server validates master_token and returns session_token
# 6. CLI saves to ~/.olav/credentials:
#    OLAV_SESSION_TOKEN=<jwt-session-token>
#    OLAV_CLIENT_ID=<unique-id>
#    OLAV_CLIENT_NAME=alice-laptop

# 7. Subsequent CLI commands automatically pick up token:
olav query "show interfaces"
#    └─> Reads ~/.olav/credentials
#    └─> Adds: Authorization: Bearer <session_token>
#    └─> Server validates JWT with JWT_SECRET_KEY from .env
#    └─> Request executed
```

---

## Key Files & Locations

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| **Server Token Generation** | `setup.ps1` | 1226-1239 | ✅ Implemented |
| **Write JWT_SECRET_KEY to .env** | `setup.ps1` | 1339 | ⚠️ May not persist |
| **Register Command** | `src/olav/cli/commands.py` | 675-730 | ✅ Implemented |
| **Register Client Function** | `src/olav/cli/commands.py` | 712-800 | ✅ Implemented |
| **Credentials Save** | `src/olav/cli/commands.py` | 750-785 | ✅ Implemented |
| **HTTP Client (register)** | `src/olav/cli/thin_client.py` | 298-327 | ✅ Implemented |
| **Bearer Token Header** | `src/olav/cli/thin_client.py` | 258-259 | ✅ Implemented |
| **Token Lookup Priority** | `src/olav/cli/commands.py` | 78-116 | ✅ Implemented |

---

## Issues & Discrepancies Found

### Issue #1: JWT_SECRET_KEY Not in Current .env
**Status**: 🔴 **CRITICAL** - **ROOT CAUSE FOUND** ✅

**Root Cause**: `Generate-EnvFile` function (QuickTest mode) is missing JWT_SECRET_KEY output
- **Expected**: `Generate-EnvFile` should include `JWT_SECRET_KEY=$($Config.JWT_SECRET_KEY)`
- **Actual**: Lines 1072-1145 in setup.ps1 never add JWT_SECRET_KEY to $envLines
- **Why**: QuickTest mode uses `Generate-EnvFile` (no JWT); Production mode uses `Generate-EnvFile-Production` (has JWT)
- **Timeline**:
  1. ✅ setup.ps1 calls `Step-TokenGeneration` (line 1570)
  2. ✅ `$Config.JWT_SECRET_KEY` is generated and stored
  3. ❌ `Generate-EnvFile` is called but **omits JWT_SECRET_KEY from output**
  4. ❌ Result: .env file created without JWT_SECRET_KEY
- **Impact**: Server cannot sign/validate JWT tokens (fatal for token system)
- **Fix Available**: See `JWT_SECRET_KEY_FIX.md` for three solution options
  - Option 1 (Quick): Manually add to .env (5 min)
  - Option 2 (Recommended): Update setup.ps1 line ~1138 (10 min)
  - Option 3 (Best): Merge both .env generation functions (20 min)

### Issue #2: Server Endpoint Verification Needed
**Status**: 🟡 **PENDING VERIFICATION**
- **Endpoint**: `POST /auth/register` (referenced in thin_client.py)
- **Status**: Client code exists but server implementation needs verification
- **Location**: Likely `src/olav/server/api/auth.py` or similar
- **Action**: Need to verify server has `/auth/register` endpoint

### Issue #3: Token Refresh Not Implemented
**Status**: 🟡 **INCOMPLETE**
- **Note**: Comments in auth.py mention "token refresh not implemented yet"
- **Impact**: Session tokens may not refresh after expiration
- **Needed**: Implement refresh endpoint and client-side refresh logic

---

## Authentication Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                    OLAV Authentication Stack                │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Tier 1: Server-Side                                         │
│  ├─ JWT_SECRET_KEY (in .env)                               │
│  ├─ Master token (from setup.ps1)                          │
│  └─ /auth/register endpoint (validates master token)        │
│                                                               │
│  Tier 2: Client Registration                                │
│  ├─ CLI: olav register --name "x" --token "master"         │
│  ├─ Server: Validates & issues session_token (JWT)         │
│  └─ Client: Saves to ~/.olav/credentials                   │
│                                                               │
│  Tier 3: Request Authentication                             │
│  ├─ CLI reads token from env/file/credentials              │
│  ├─ Adds: Authorization: Bearer {token}                    │
│  └─ Server validates with JWT_SECRET_KEY                   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Recommendations

1. **Immediate**: Verify JWT_SECRET_KEY in current `.env`
   - Check: `cat .env | grep JWT_SECRET_KEY`
   - If missing: Re-run `setup.ps1` Step-TokenGeneration

2. **Verify Server Endpoint**: Confirm `/auth/register` exists
   - Check server logs for endpoint registration
   - Test: `curl -X POST http://localhost:8000/auth/register -H "Content-Type: application/json" -d '{"client_name": "test", "master_token": "xxx"}'`

3. **Implement Token Refresh**: Add refresh endpoint
   - Server: `/auth/refresh` to validate expired tokens
   - Client: Auto-refresh logic in AuthClient

4. **Test Registration Flow**:
   ```bash
   # Test the complete flow
   olav register --name "test-client" --token "$env:MASTER_TOKEN"
   # Check: ~/.olav/credentials should have OLAV_SESSION_TOKEN
   cat ~/.olav/credentials
   ```
