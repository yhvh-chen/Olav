# Testing API Documentation

## Quick Start (1 minute)

### 1. Start API Server

```bash
# Terminal 1: Start server
uv run python -m olav.server.app
```

Expected output:
```
🚀 Starting OLAV API Server...
✅ LangServe routes added: /orchestrator/invoke, /orchestrator/stream
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 2. Test OpenAPI Documentation

```bash
# Terminal 2: Run test script
uv run python scripts/test_openapi_docs.py
```

Expected output:
```
✓ Title: OLAV API - Enterprise Network Operations Platform
✓ Version: 0.4.0-beta
✓ Description: 1200+ characters

OpenAPI Tags:
┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Name        ┃ Description                             ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ auth        │ 🔐 Authentication operations...         │
│ monitoring  │ 📊 Health checks...                     │
│ orchestrator│ 🤖 Workflow execution...                │
└─────────────┴─────────────────────────────────────────┘

Registered Endpoints: 6
  GET /health - Health check endpoint
  POST /auth/login - User authentication
  GET /status - Get server status with user info
  GET /me - Get current user info
  POST /orchestrator/invoke - Workflow execution (non-streaming)
  POST /orchestrator/stream - Workflow execution (streaming)

Checking Response Examples...
  ✓ GET /health (200) has example
  ✓ GET /health (503) has example
  ✓ POST /auth/login (200) has example
  ✓ POST /auth/login (401) has example
  ✓ GET /status (200) has example
  ✓ GET /status (401) has example
  ✓ GET /me (200) has example
  ✓ GET /me (401) has example

Total Examples Found: 8

✓ Swagger UI accessible at http://localhost:8000/docs
✓ ReDoc accessible at http://localhost:8000/redoc

Test Results Summary:
✓ PASS OpenAPI Schema
✓ PASS Swagger UI
✓ PASS ReDoc

Total: 3/3 tests passed
```

### 3. Interactive Testing in Swagger UI

Open browser: **http://localhost:8000/docs**

#### Test Authentication Flow:

1. **Expand POST /auth/login**
2. Click **"Try it out"**
3. Use demo credentials:
   ```json
   {
     "username": "admin",
     "password": "admin123"
   }
   ```
4. Click **"Execute"**
5. Copy `access_token` from response

#### Test Protected Endpoints:

1. **Click "Authorize" button** (top right, 🔓 icon)
2. Paste token in format: `Bearer eyJ0eXAi...`
3. Click **"Authorize"**
4. Now test protected endpoints (GET /status, GET /me)

## Validation Checklist

### OpenAPI Schema ✅
- [x] Title: "OLAV API - Enterprise Network Operations Platform"
- [x] Version: "0.4.0-beta"
- [x] Description: Multi-paragraph with features, Quick Start, authentication
- [x] Tags: auth, monitoring, orchestrator (with emoji icons)
- [x] Contact info: OLAV Development Team
- [x] License: Proprietary

### Endpoint Documentation ✅
- [x] GET /health: Public health check with 200/503 examples
- [x] POST /auth/login: JWT authentication with demo credentials
- [x] GET /status: Server status + user info with auth header example
- [x] GET /me: Current user info with curl example
- [x] POST /orchestrator/invoke: Workflow execution (non-streaming)
- [x] POST /orchestrator/stream: Workflow execution (SSE streaming)

### Response Examples ✅
- [x] 8 total examples across endpoints
- [x] Success responses (200) with realistic data
- [x] Error responses (401, 503) with error formats
- [x] Pydantic models with Field descriptions and examples

### Interactive Docs ✅
- [x] Swagger UI accessible at /docs
- [x] ReDoc accessible at /redoc
- [x] "Try it out" functionality enabled
- [x] Authorization button for JWT tokens

## Manual Testing Steps

### 1. Test Health Check (No Auth)

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "version": "0.4.0-beta",
  "environment": "production",
  "postgres_connected": true,
  "orchestrator_ready": true
}
```

### 2. Test Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

Expected response:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

### 3. Test Protected Endpoint

```bash
# Replace TOKEN with actual token from login response
export TOKEN="eyJ0eXAi..."

curl http://localhost:8000/me \
  -H "Authorization: Bearer $TOKEN"
```

Expected response:
```json
{
  "username": "admin",
  "role": "admin",
  "disabled": false
}
```

### 4. Test Invalid Token

```bash
curl http://localhost:8000/me \
  -H "Authorization: Bearer invalid_token"
```

Expected response (401):
```json
{
  "detail": "Could not validate credentials"
}
```

## Documentation URLs

- **Swagger UI**: http://localhost:8000/docs
  - Interactive API testing
  - "Try it out" functionality
  - Request/response examples

- **ReDoc**: http://localhost:8000/redoc
  - Better readability
  - Cleaner layout
  - PDF-friendly

- **OpenAPI JSON**: http://localhost:8000/openapi.json
  - Raw schema for tools
  - Import into Postman/Insomnia

- **API Usage Guide**: `docs/API_USAGE.md`
  - Comprehensive reference
  - Python SDK examples
  - CLI integration guide
  - Deployment instructions

## Troubleshooting

### Server Won't Start

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check environment variables
uv run python -c "from config.settings import EnvSettings; print(EnvSettings())"

# View detailed logs
uv run python -m olav.server.app --log-level debug
```

### OpenAPI Schema Not Loading

```bash
# Verify server is healthy
curl http://localhost:8000/health

# Check OpenAPI endpoint directly
curl http://localhost:8000/openapi.json | jq .info

# Clear browser cache and reload /docs
```

### Examples Not Showing in Swagger UI

1. Hard refresh browser: `Ctrl+Shift+R` (Windows) or `Cmd+Shift+R` (Mac)
2. Check OpenAPI schema has examples:
   ```bash
   curl http://localhost:8000/openapi.json | jq '.paths."/auth/login".post.responses."200".content'
   ```
3. Verify FastAPI version: `uv run python -c "import fastapi; print(fastapi.__version__)"`
   - Should be >= 0.115.0

## Next Steps After Validation

### If All Tests Pass ✅

1. **Mark Task 29 Complete**
2. **Move to Task 10**: E2E Integration Testing
   - Create `tests/e2e/test_langserve_api.py`
   - Test full authentication flow
   - Test workflow execution endpoints
   - Test CLI client with --server parameter
   - Target: 8-10 comprehensive tests

### If Tests Fail ❌

1. **Check server logs** for errors
2. **Verify dependencies**: `uv sync`
3. **Test individual endpoints** with curl
4. **Review app.py** for syntax errors
5. **Restart server** and retry

## Success Criteria

✅ All 3 test categories pass (OpenAPI Schema, Swagger UI, ReDoc)
✅ 8+ response examples visible in OpenAPI schema
✅ Interactive testing works in Swagger UI (/docs)
✅ Authentication flow completes successfully
✅ Protected endpoints return 401 without token
✅ curl examples from API_USAGE.md work correctly

**Current Status**: Task 29 at 90% completion - pending live server validation
