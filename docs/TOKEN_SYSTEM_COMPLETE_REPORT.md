# OLAV Token System - Complete Investigation Report

## Executive Summary

✅ **Investigation Complete** - Found critical JWT_SECRET_KEY bug in setup.ps1

**Key Findings**:
1. ✅ Complete authentication architecture is well-designed
2. ✅ Client-side credentials storage properly implemented
3. ✅ Bearer token mechanism correctly coded
4. 🔴 **Critical Bug**: JWT_SECRET_KEY missing from QuickTest mode .env file
5. 🟡 Server authentication endpoints need verification

---

## Architecture Overview

### Three-Tier Token System

```
┌─────────────────────────────────────────────┐
│         OLAV Authentication Stack           │
├─────────────────────────────────────────────┤
│                                              │
│  TIER 1: Server Token Management            │
│  ├─ JWT_SECRET_KEY: Server signing key      │
│  ├─ Master Token: One-time setup token      │
│  └─ Location: .env (JWT_SECRET_KEY)         │
│                                              │
│  TIER 2: Client Registration                │
│  ├─ Command: olav register --name X         │
│  ├─ Result: Session token (JWT)             │
│  └─ Storage: ~/.olav/credentials            │
│                                              │
│  TIER 3: API Authentication                 │
│  ├─ Header: Authorization: Bearer {token}   │
│  ├─ Validation: JWT_SECRET_KEY check        │
│  └─ Scope: All API requests                 │
│                                              │
└─────────────────────────────────────────────┘
```

### Token Flow Diagram

```
┌──────────────┐                ┌──────────────┐
│  OLAV Setup  │                │  OLAV Server │
│  (setup.ps1) │                │              │
└──────┬───────┘                └──────┬───────┘
       │                               │
       │ 1. Generate JWT_SECRET_KEY    │
       ├──────────────────────────────>│
       │                               │
       │ 2. Store in .env              │
       │ (CRITICAL: QuickTest bug)     │
       │                               │
       │ 3. Start server               │
       ├──────────────────────────────>│
       │    Load JWT_SECRET_KEY        │
       │                               │
       └───────────────┬───────────────┘
                       │
                  ┌────▼─────────┐
                  │  CLI Client  │
                  └────┬─────────┘
                       │
                       │ 1. olav register --name "laptop" --token "master"
                       │    (Sends POST /auth/register)
                       │
                  ┌────▼─────────────────────┐
                  │ 2. Server receives       │
                  │    - Validates master    │
                  │    - Creates JWT token   │
                  │    - Signs with SECRET_KEY
                  └────┬─────────────────────┘
                       │
                       │ 3. Returns session_token
                       │
                  ┌────▼─────────────────────┐
                  │ 4. CLI saves to          │
                  │    ~/.olav/credentials   │
                  └────┬─────────────────────┘
                       │
                       │ 5. Subsequent queries
                       │    - Read token from credentials
                       │    - Add: Authorization: Bearer {token}
                       │    - Server validates with JWT_SECRET_KEY
                       │    - Request executed
                       │
                       ▼
```

---

## Detailed Component Analysis

### 1. Server-Side Setup (setup.ps1)

**Token Generation**:
```powershell
# Step-TokenGeneration (line 1226-1239)
function Step-TokenGeneration {
    # Generates 32-byte random value, base64-encoded
    $Config.JWT_SECRET_KEY = [System.Convert]::ToBase64String(
        [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
    )
}
```
✅ **Status**: Working correctly - generates cryptographically secure random token

**ENV File Generation**:
```powershell
# QuickTest Mode (line 1072-1145)
function Generate-EnvFile {
    # Missing JWT_SECRET_KEY ❌
}

# Production Mode (line 1267-1360)
function Generate-EnvFile-Production {
    # Includes: JWT_SECRET_KEY=$($Config.JWT_SECRET_KEY) ✅ (line 1344)
}
```
🔴 **Status**: CRITICAL BUG in QuickTest mode - JWT_SECRET_KEY not included

### 2. Client Registration (CLI)

**Registration Command** (`src/olav/cli/commands.py`):
```python
# olav register --name "my-laptop" --token "master-token"
@command
def register(
    name: str,           # Client identifier
    token: str | None,   # Master token (from server)
    server: str | None,  # Server URL
    save: bool = True    # Save credentials flag
) -> None:
    """Register this client with server"""
```
✅ **Status**: Fully implemented with proper CLI interface

**Registration Flow** (`_register_client` function):
```python
async def _register_client(client_name, master_token, server_url, save_credentials):
    # 1. Connect to server
    async with OlavThinClient(config, auth_token=None) as client:
        # 2. Check server health
        health = await client.health()
        
        # 3. Register and get session token
        result = await client.register(client_name, master_token)
        
        # 4. Extract: session_token, client_id, expires_at
        session_token = result["session_token"]
        
        # 5. Save to ~/.olav/credentials
        if save_credentials:
            credentials["OLAV_SESSION_TOKEN"] = session_token
            credentials["OLAV_CLIENT_ID"] = client_id
            credentials["OLAV_CLIENT_NAME"] = client_name
```
✅ **Status**: Properly designed with error handling

**HTTP Endpoint** (`src/olav/cli/thin_client.py`):
```python
async def register(self, client_name: str, master_token: str) -> dict:
    """POST /auth/register"""
    payload = {
        "client_name": client_name,
        "master_token": master_token,
    }
    response = await self._client.post("/auth/register", json=payload)
    return response.json()
```
✅ **Status**: Clean implementation, expects `/auth/register` endpoint

### 3. Credentials Storage (Client-Side)

**Location**: `~/.olav/credentials` (home directory)

**Format**: INI-style key=value
```ini
OLAV_SESSION_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
OLAV_CLIENT_ID=client-abc-123-def
OLAV_CLIENT_NAME=alice-laptop
```

**Permissions**: 
- Unix: 0600 (user-only read/write)
- Windows: Inherits from user profile security

**Management** (`src/olav/cli/commands.py` lines 750-785):
```python
credentials_dir = Path.home() / ".olav"
credentials_dir.mkdir(exist_ok=True)
credentials_file = credentials_dir / "credentials"

# Load existing credentials
if credentials_file.exists():
    # Parse key=value pairs
    ...

# Update with new session token
credentials["OLAV_SESSION_TOKEN"] = session_token

# Write back with secure handling
with open(credentials_file, "w") as f:
    f.write("# OLAV Client Credentials\n")
    f.write("# Auto-generated by 'olav register'\n\n")
    for k, v in credentials.items():
        f.write(f"{k}={v}\n")
```
✅ **Status**: Properly implemented with comments and structure

### 4. Request Authentication

**Token Lookup Priority** (`src/olav/cli/commands.py` lines 78-116):
```python
def _get_config_from_env(server_url: str | None):
    """Resolve auth token with priority"""
    auth_token = (
        os.getenv("OLAV_API_TOKEN")           # 1. Environment variable (highest)
        or env_vars.get("OLAV_API_TOKEN")     # 2. From .env file
        or credentials.get("OLAV_SESSION_TOKEN")  # 3. From ~/.olav/credentials
    )
    return config, auth_token
```
✅ **Status**: Sensible priority order with fallback chain

**Bearer Token Header** (`src/olav/cli/thin_client.py` lines 250-270):
```python
async def _build_headers(self) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if self.auth_token:
        headers["Authorization"] = f"Bearer {self.auth_token}"
    return headers
```
✅ **Status**: Correct RFC 6750 Bearer Token format

**All API Requests**:
```python
# Every request includes Bearer header
response = await self._client.post(endpoint, headers=headers, json=payload)
```
✅ **Status**: Consistently applied to all requests

---

## Current Environment Status

### .env File (c:\Users\yhvh\Documents\code\Olav\.env)

```dotenv
# Generated by Setup Wizard (Quick Test Mode)
# Generated: 2025-12-10 20:13:17

OLAV_MODE=quicktest

# LLM Configuration
LLM_PROVIDER=openai
LLM_API_KEY=sk-or-v1-...
LLM_MODEL_NAME=x-ai/grok-4.1-fast

# Device Credentials
DEVICE_USERNAME=cisco
DEVICE_PASSWORD=cisco

# NetBox
NETBOX_URL=http://netbox:8080
NETBOX_TOKEN=0123456789abcdef0123456789abcdef01234567
NETBOX_SECRET_KEY=2218b4b76c3a4c71a8591ab7c9db6c1bc3b2f45460bf4715b479f0db39915b0f

# PostgreSQL
POSTGRES_USER=olav
POSTGRES_PASSWORD=olav

# OpenSearch
OPENSEARCH_SECURITY_DISABLED=true

# Port Configuration
OPENSEARCH_PORT=19200
POSTGRES_PORT=55432
NETBOX_PORT=8080
```

**Missing**: 🔴 `JWT_SECRET_KEY=...` ❌

---

## Critical Issues Found

### Issue #1: JWT_SECRET_KEY Missing from QuickTest .env 🔴 CRITICAL

**Status**: Root cause identified, fix provided

**Root Cause Chain**:
1. ✅ `Step-TokenGeneration` generates `$Config.JWT_SECRET_KEY` (32-byte base64)
2. ✅ setup.ps1 calls function and stores in `$Config` hashtable
3. ❌ `Generate-EnvFile` function (lines 1072-1145) doesn't output JWT_SECRET_KEY
4. ❌ Result: .env file created without JWT_SECRET_KEY
5. ❌ Server cannot validate tokens (fatal error)

**Evidence**:
```powershell
# Lines 1138-1145 in setup.ps1
$envLines += @(
    ""
    "# Port Configuration"
    "OPENSEARCH_PORT=$($Config.OPENSEARCH_PORT)"
    "POSTGRES_PORT=$($Config.POSTGRES_PORT)"
    "NETBOX_PORT=$($Config.NETBOX_PORT)"
)
# ❌ JWT_SECRET_KEY is never added!
```

**Comparison**:
- Production mode (`Generate-EnvFile-Production`, line 1344): ✅ Includes JWT_SECRET_KEY
- QuickTest mode (`Generate-EnvFile`, line 1072-1145): ❌ Missing JWT_SECRET_KEY

**Impact**: Without JWT_SECRET_KEY in .env:
- ❌ Server cannot initialize JWT library
- ❌ Cannot sign session tokens during registration
- ❌ Cannot validate bearer tokens on API requests
- ❌ Complete authentication failure

**Solution**: See `JWT_SECRET_KEY_FIX.md` for three fix options

### Issue #2: Server Endpoints Need Verification 🟡 PENDING

**Endpoints Required**:
1. `POST /auth/register` - Client registration
   - Input: `{client_name, master_token}`
   - Output: `{session_token, client_id, client_name, expires_at}`
   - Status: ✅ Coded in client, ❓ server implementation unknown

2. `GET /health` - Server health check
   - Input: None
   - Output: `{status}`
   - Status: ✅ Coded in client (`OlavThinClient.health()`), ❓ server implementation unknown

3. Token validation on all endpoints
   - Check: `Authorization: Bearer {token}` header
   - Validate: JWT signature with JWT_SECRET_KEY
   - Status: ❓ Unknown if implemented on server

**Recommendation**: Verify server has these endpoints before testing authentication

### Issue #3: Token Refresh Not Implemented 🟡 INCOMPLETE

**Status**: No refresh mechanism found

**Observations**:
- Credentials stored with `expires_at` timestamp
- No automatic refresh logic in client
- No refresh endpoint referenced in code
- Comments suggest "not implemented yet"

**Impact**:
- Session tokens expire but won't auto-refresh
- User gets authentication error after expiration
- Must re-register to get new token

**Recommendation**: Implement token refresh endpoint and client-side refresh logic

---

## File Reference Map

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| **Token Generation** | `setup.ps1` | 1226-1239 | ✅ Works |
| **QuickTest .env Gen** | `setup.ps1` | 1072-1145 | 🔴 **BUG: Missing JWT** |
| **Production .env Gen** | `setup.ps1` | 1267-1360 | ✅ Has JWT |
| **Register Command** | `src/olav/cli/commands.py` | 675-730 | ✅ Implemented |
| **Register Logic** | `src/olav/cli/commands.py` | 712-800 | ✅ Implemented |
| **Cred Save** | `src/olav/cli/commands.py` | 750-785 | ✅ Implemented |
| **Token Priority** | `src/olav/cli/commands.py` | 78-116 | ✅ Implemented |
| **HTTP Register** | `src/olav/cli/thin_client.py` | 298-327 | ✅ Implemented |
| **Bearer Header** | `src/olav/cli/thin_client.py` | 258-259 | ✅ Implemented |
| **Health Check** | `src/olav/cli/thin_client.py` | 290-297 | ✅ Implemented |

---

## Recommendations

### Immediate Actions (Today)

1. **Fix JWT_SECRET_KEY Bug** (10 minutes)
   ```powershell
   # Option 1 (Quick): Add to .env manually
   JWT_SECRET_KEY=<generate-via-powershell>
   
   # Option 2 (Recommended): Update setup.ps1 line ~1138
   # Add section before "# Port Configuration"
   ```

2. **Verify Server Endpoints** (15 minutes)
   - Check: `/auth/register` implementation exists
   - Test: `curl -X POST http://localhost:8000/auth/register ...`
   - Verify: Returns `{session_token, client_id, expires_at}`

3. **Test Authentication Flow** (20 minutes)
   ```bash
   # Test complete flow
   olav register --name "test-client" --token "$env:MASTER_TOKEN"
   # Check: ~/.olav/credentials has OLAV_SESSION_TOKEN
   cat ~/.olav/credentials
   # Test: Query with auto-loaded token
   olav query "show interfaces"
   ```

### Short-term Improvements (This Week)

1. **Implement Token Refresh**
   - Server endpoint: `POST /auth/refresh`
   - Client: Auto-refresh before expiration
   - Update credentials file with new token

2. **Add Server Endpoint Documentation**
   - Document auth endpoints in API docs
   - Verify JWT library integration
   - Add example requests

3. **Consolidate .env Functions**
   - Merge `Generate-EnvFile` and `Generate-EnvFile-Production`
   - Eliminate duplication (DRY principle)
   - Reduce maintenance burden

### Long-term Architecture

1. **Audit JWT Implementation**
   - Algorithm: Should be HS256 or RS256
   - Expiration: Recommend 24 hours for sessions
   - Refresh: Implement with longer TTL

2. **Add API Key Alternative**
   - Support both JWT and API keys
   - Better for automation/CI/CD
   - Easier key rotation

3. **Enhance Credential Security**
   - Consider encrypting ~/.olav/credentials
   - Add credential expiration warnings
   - Implement credential rotation policy

---

## Testing Checklist

- [ ] JWT_SECRET_KEY added to .env
- [ ] setup.ps1 generates JWT_SECRET_KEY in QuickTest mode
- [ ] Server can start with JWT_SECRET_KEY from .env
- [ ] `olav register` command works end-to-end
- [ ] Session token saved to ~/.olav/credentials
- [ ] CLI uses token from credentials file automatically
- [ ] Bearer header sent on all requests
- [ ] Server validates token with JWT_SECRET_KEY
- [ ] Token refresh works (if implemented)
- [ ] Credentials expire after TTL

---

## References

- **JWT Standard**: RFC 7519
- **Bearer Token**: RFC 6750
- **Python JWT**: PyJWT documentation
- **Setup.ps1**: `setup.ps1` lines 1226-1360
- **CLI Auth**: `src/olav/cli/auth.py`, `src/olav/cli/commands.py`
- **Thin Client**: `src/olav/cli/thin_client.py`

---

## Summary

✅ **Good News**: Authentication architecture is well-designed and mostly implemented
🔴 **Critical Bug**: JWT_SECRET_KEY missing from QuickTest mode .env
🟡 **Action Items**: Fix bug, verify server endpoints, implement token refresh

**Estimated Fix Time**: 10-30 minutes depending on approach chosen
**Risk Level**: Low (isolated bug, well-understood solution)
**Impact**: High (required for any authentication to work)
