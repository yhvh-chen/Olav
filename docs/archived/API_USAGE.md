# OLAV API Usage Guide

**Version**: 0.4.0-beta  
**Last Updated**: 2025-11-24

---

## Overview

OLAV API provides LangServe-based HTTP/WebSocket endpoints for enterprise network operations. The API supports:

- **Authentication**: JWT-based with role-based access control (RBAC)
- **Workflows**: Query diagnostics, device execution, NetBox management, and deep dive analysis
- **Streaming**: Real-time SSE (Server-Sent Events) for long-running workflows
- **HITL**: Human-in-the-loop approval for write operations

**Base URL**: `http://localhost:8000` (default)  
**Production**: `https://olav-api.company.com`

---

## Quick Start

### 1. Start the Server

```bash
# Using Docker Compose (recommended)
docker-compose up -d olav-server

# Or run directly with uv
uv run python src/olav/server/app.py
```

**Server Status**:
```bash
curl http://localhost:8000/health
```

**Response**:
```json
{
  "status": "healthy",
  "version": "0.4.0-beta",
  "environment": "development",
  "orchestrator_ready": true
}
```

### 2. Authenticate

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"
```

**Response**:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiIsImV4cCI6MTcwMDg1MDAwMH0.xxxxx",
  "token_type": "bearer"
}
```

**Save the token** for subsequent requests.

### 3. Execute Workflow Query

```bash
curl -X POST http://localhost:8000/orchestrator/invoke \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "messages": [
        {"role": "user", "content": "查询 R1 的接口状态"}
      ]
    },
    "config": {
      "configurable": {
        "thread_id": "test-session-001"
      }
    }
  }'
```

**Response**:
```json
{
  "output": {
    "messages": [
      {
        "type": "human",
        "content": "查询 R1 的接口状态"
      },
      {
        "type": "ai",
        "content": "根据 SuzieQ 查询结果，R1 设备有以下接口...\n\n| 接口 | 状态 | IP 地址 |\n|------|------|--------|\n| GigabitEthernet0/0 | up | 10.1.1.1/24 |"
      }
    ]
  },
  "metadata": {
    "run_id": "abc-123-def"
  }
}
```

---

## Authentication

### Login

**Endpoint**: `POST /auth/login`

**Request**:
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"
```

**Parameters**:
- `username` (string, required): Username
- `password` (string, required): Password

**Response** (200 OK):
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGci...",
  "token_type": "bearer"
}
```

**Error Responses**:
- `401 Unauthorized`: Invalid credentials
- `422 Validation Error`: Missing username/password

**Available Users** (demo):
| Username | Password | Role |
|----------|----------|------|
| admin | admin123 | admin |
| operator | operator123 | operator |
| viewer | viewer123 | viewer |

### Using JWT Token

Include the token in the `Authorization` header for all protected endpoints:

```bash
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGci...
```

**Token Expiration**: 60 minutes (default)

---

## Core Endpoints

### Health Check

**Endpoint**: `GET /health`

**Authentication**: Not required (public)

**Request**:
```bash
curl http://localhost:8000/health
```

**Response** (200 OK):
```json
{
  "status": "healthy",
  "version": "0.4.0-beta",
  "environment": "development",
  "orchestrator_ready": true
}
```

**Use Case**: Server monitoring, readiness checks

---

### Current User Info

**Endpoint**: `GET /me`

**Authentication**: Required

**Request**:
```bash
curl http://localhost:8000/me \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Response** (200 OK):
```json
{
  "username": "admin",
  "role": "admin"
}
```

**Error Responses**:
- `401 Unauthorized`: Missing or invalid token

---

### Server Status

**Endpoint**: `GET /status`

**Authentication**: Required

**Request**:
```bash
curl http://localhost:8000/status \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Response** (200 OK):
```json
{
  "status": "operational",
  "orchestrator": "ready",
  "workflows": ["query", "execution", "netbox", "deepdive"],
  "checkpointer": "postgresql",
  "backend": "opensearch"
}
```

---

## Workflow Execution

### Invoke (Non-Streaming)

**Endpoint**: `POST /orchestrator/invoke`

**Authentication**: Required

**Request**:
```bash
curl -X POST http://localhost:8000/orchestrator/invoke \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "messages": [
        {"role": "user", "content": "查询所有边界路由器 BGP 状态"}
      ]
    },
    "config": {
      "configurable": {
        "thread_id": "session-123"
      }
    }
  }'
```

**Request Body**:
```typescript
{
  input: {
    messages: Array<{
      role: "user" | "assistant" | "system",
      content: string
    }>
  },
  config: {
    configurable: {
      thread_id: string  // Conversation session ID
    }
  }
}
```

**Response** (200 OK):
```json
{
  "output": {
    "messages": [
      {"type": "human", "content": "查询所有边界路由器 BGP 状态"},
      {"type": "ai", "content": "已分析 5 台边界路由器的 BGP 状态..."}
    ]
  },
  "metadata": {
    "run_id": "uuid",
    "workflow": "QueryDiagnosticWorkflow"
  }
}
```

**Use Cases**:
- One-shot queries
- Simple diagnostics
- Batch processing

---

### Stream (Real-Time Streaming)

**Endpoint**: `POST /orchestrator/stream`

**Authentication**: Required

**Request**:
```bash
curl -X POST http://localhost:8000/orchestrator/stream \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "messages": [
        {"role": "user", "content": "审计所有路由器配置合规性"}
      ]
    },
    "config": {
      "configurable": {
        "thread_id": "audit-2025-11-24"
      }
    }
  }'
```

**Response** (200 OK, Server-Sent Events):
```
event: data
data: {"messages": [{"type": "ai", "content": "正在初始化审计流程..."}]}

event: data
data: {"messages": [{"type": "ai", "content": "已扫描 10/50 设备..."}]}

event: data
data: {"messages": [{"type": "ai", "content": "发现 3 个合规性问题..."}]}

event: end
```

**Use Cases**:
- Long-running workflows (>30 seconds)
- Progress tracking
- Interactive diagnostics
- Deep dive analysis

**Client Implementation** (Python):
```python
import httpx

async with httpx.AsyncClient() as client:
    async with client.stream(
        "POST",
        "http://localhost:8000/orchestrator/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"input": {...}, "config": {...}},
        timeout=300.0,
    ) as response:
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                print(data["messages"][-1]["content"])
```

---

## Python SDK Usage

### Using LangServe RemoteRunnable

**Installation**:
```bash
pip install langserve httpx
```

**Basic Usage**:
```python
from langserve import RemoteRunnable

# Create client
orchestrator = RemoteRunnable(
    "http://localhost:8000/orchestrator",
    headers={"Authorization": "Bearer YOUR_ACCESS_TOKEN"}
)

# Invoke (non-streaming)
result = await orchestrator.ainvoke({
    "messages": [{"role": "user", "content": "查询 R1"}]
}, config={"configurable": {"thread_id": "session-1"}})

print(result["messages"][-1]["content"])
```

**Streaming**:
```python
async for chunk in orchestrator.astream(
    {"messages": [{"role": "user", "content": "复杂查询"}]},
    config={"configurable": {"thread_id": "session-1"}}
):
    if "messages" in chunk:
        latest_msg = chunk["messages"][-1]
        print(latest_msg["content"])
```

**With Authentication Manager**:
```python
from langserve import RemoteRunnable
import httpx
import json

# Login to get token
async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8000/auth/login",
        data={"username": "admin", "password": "admin123"}
    )
    token = response.json()["access_token"]

# Use token with RemoteRunnable
orchestrator = RemoteRunnable(
    "http://localhost:8000/orchestrator",
    headers={"Authorization": f"Bearer {token}"}
)

# Execute query
result = await orchestrator.ainvoke({"messages": [...]})
```

---

## OLAV CLI Integration

### Login

```bash
uv run python cli.py login
# Server URL: http://localhost:8000
# Username: admin
# Password: ****
# ✅ Successfully logged in as admin
```

**Credentials stored** in `~/.olav/credentials`:
```json
{
  "server_url": "http://localhost:8000",
  "access_token": "eyJ0eXAi...",
  "token_type": "bearer",
  "expires_at": "2025-11-24T23:00:00",
  "username": "admin"
}
```

### Execute Query (Authenticated)

```bash
# Remote mode (uses stored token)
uv run python cli.py "查询 R1 接口状态"

# Local mode (no authentication)
uv run python cli.py -L "查询 R1"

# Custom server
uv run python cli.py --server https://prod-olav.company.com "查询"
```

### Check Status

```bash
uv run python cli.py whoami
# ✅ Authenticated
# Username: admin
# Server: http://localhost:8000
# Expires in: 45 minutes
```

### Logout

```bash
uv run python cli.py logout
# ✅ Successfully logged out
# Credentials removed from ~/.olav/credentials
```

---

## RBAC (Role-Based Access Control)

### Roles

| Role | Permissions | Use Case |
|------|-------------|----------|
| **admin** | Full access (read + write + approve) | System administrators |
| **operator** | Read + write (requires approval for critical ops) | Network operators |
| **viewer** | Read-only | Monitoring, auditing |

### Permission Matrix

| Action | Admin | Operator | Viewer |
|--------|-------|----------|--------|
| Query diagnostics | ✅ | ✅ | ✅ |
| Device execution (read) | ✅ | ✅ | ✅ |
| Device execution (write) | ✅ | ✅ (HITL) | ❌ |
| NetBox management | ✅ | ✅ (HITL) | ❌ |
| Deep dive workflow | ✅ | ✅ | ✅ |
| Approve HITL requests | ✅ | ❌ | ❌ |

### HITL (Human-in-the-Loop)

**Write operations require approval**:
```bash
# Operator submits config change
POST /orchestrator/stream
{
  "messages": [{"role": "user", "content": "修改 R1 BGP AS 号为 65001"}]
}

# Response: Workflow paused, waiting for approval
{
  "messages": [
    {"type": "ai", "content": "检测到配置变更，需要管理员批准..."},
    {"type": "ai", "content": "变更内容: router bgp 65001"}
  ],
  "interrupted": true,
  "approval_required": true
}

# Admin approves (separate endpoint, future implementation)
POST /orchestrator/approve
{
  "thread_id": "session-123",
  "decision": "approve"
}
```

---

## Error Handling

### Common HTTP Status Codes

| Code | Meaning | Solution |
|------|---------|----------|
| 200 | Success | - |
| 401 | Unauthorized | Check Authorization header, re-login |
| 403 | Forbidden | Insufficient permissions (RBAC) |
| 422 | Validation Error | Check request body format |
| 500 | Internal Server Error | Check server logs |

### Error Response Format

```json
{
  "detail": "Authentication required",
  "error_code": "UNAUTHORIZED",
  "timestamp": "2025-11-24T12:00:00Z"
}
```

### Debugging

**Enable verbose logging** (server):
```bash
export LOG_LEVEL=DEBUG
uv run python src/olav/server/app.py
```

**Check server logs**:
```bash
docker-compose logs -f olav-server
```

---

## Best Practices

### 1. Token Management

**DO**:
- Store tokens securely (environment variables, credential files)
- Set short expiration times (60 minutes default)
- Implement token refresh logic

**DON'T**:
- Hardcode tokens in source code
- Share tokens across users
- Log tokens in plaintext

### 2. Thread IDs

**Use meaningful thread IDs** for conversation tracking:
```python
import uuid

# Good: Persistent session
thread_id = f"user-{username}-{session_start}"

# Good: Task-based
thread_id = f"audit-{device_name}-{date}"

# Bad: Random UUID (can't resume)
thread_id = str(uuid.uuid4())
```

### 3. Streaming vs. Non-Streaming

**Use Streaming** when:
- Query takes >5 seconds
- Need progress updates
- Interactive user experience

**Use Non-Streaming** when:
- Batch processing
- Background jobs
- Simple queries (<5 seconds)

### 4. Error Retry Logic

```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def query_with_retry(token: str, query: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/orchestrator/invoke",
            headers={"Authorization": f"Bearer {token}"},
            json={"input": {"messages": [{"role": "user", "content": query}]}},
            timeout=60.0
        )
        response.raise_for_status()
        return response.json()
```

---

## API Reference (OpenAPI)

**Interactive Documentation**:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

**Example Usage** (Swagger UI):
1. Navigate to `http://localhost:8000/docs`
2. Click **Authorize** button
3. Enter: `Bearer YOUR_ACCESS_TOKEN`
4. Try out endpoints interactively

---

## Deployment

### Docker Compose (Production)

```yaml
version: '3.8'

services:
  olav-server:
    image: olav-server:latest
    ports:
      - "8000:8000"
    environment:
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - POSTGRES_URI=${POSTGRES_URI}
      - OPENSEARCH_URL=${OPENSEARCH_URL}
    depends_on:
      - postgres
      - opensearch
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Environment Variables

**Required**:
```bash
# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Authentication
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60

# Database
POSTGRES_URI=postgresql://user:pass@localhost:5432/olav

# Search
OPENSEARCH_URL=http://localhost:9200

# LLM
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
```

**Optional**:
```bash
# Features
OLAV_USE_DYNAMIC_ROUTER=true
JWT_REFRESH_THRESHOLD_MINUTES=5

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

---

## Support

**Documentation**:
- Architecture: `docs/AGENT_ARCHITECTURE_REFACTOR.md`
- Design: `docs/DESIGN.md`
- Quick Start: `QUICKSTART.md`

**Issue Tracking**:
- Known Issues: `docs/KNOWN_ISSUES_AND_TODO.md`
- GitHub Issues: (repository URL)

**Contact**:
- Team: Network Automation Team
- Email: support@company.com
