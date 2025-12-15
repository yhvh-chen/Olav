# OLAV Quick Start Guide

## ✅ System Status

All OLAV components are initialized and verified:
- ✅ PostgreSQL Checkpointer (LangGraph state persistence)
- ✅ OpenSearch Indices (schema + RAG knowledge base)
- ✅ NetBox (network inventory)
- ✅ SuzieQ (network diagnostics)

---

## 🚀 Quick Start Commands

### 1. Verify Initialization (Anytime)
```bash
cd c:\Users\yhvh\Documents\code\Olav
uv run python scripts/verify_initialization.py
```

### 2. Start OLAV Normal Mode (Network Queries & Execution)
```bash
cd c:\Users\yhvh\Documents\code\Olav
uv run python -m olav.cli
```

**Examples:**
```bash
# Query network state (read-only, no approval needed)
uv run python -m olav.cli "查询 R1 接口状态"
uv run python -m olav.cli "show BGP neighbors on router1"

# Execute configuration (write operation, requires HITL approval)
uv run python -m olav.cli "修改 R1 BGP AS 号为 65001"
```

### 3. Start OLAV Expert Mode (Deep Dive - Complex Diagnostics)
```bash
# Expert mode with task decomposition, batch audits, recursive diagnostics
uv run python -m olav.cli -e "审计所有边界路由器 BGP 配置问题"
```

### 4. Access Web Interfaces

| Service | URL | Credentials |
|---------|-----|-------------|
| **NetBox** | http://localhost:8080 | admin / admin |
| **SuzieQ Dashboard** | http://localhost:8501 | (no auth) |
| **OpenSearch Dashboards** | http://localhost:5601 | (no auth required) |
| **OLAV API** | http://localhost:8000 | (FastAPI docs) |
| **OLAV Server** | http://localhost:8001 | (Backend server) |

### 5. Run Test Suite
```bash
# Unit tests
uv run pytest tests/unit/ -v

# Integration tests (requires infrastructure)
uv run pytest tests/e2e/ -v

# Full coverage report
uv run pytest --cov=src/olav --cov-report=html
```

---

## 📦 Docker Management

### View Service Status
```bash
docker-compose ps
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f olav-app
docker-compose logs -f postgres
docker-compose logs -f opensearch
```

### Restart Services
```bash
docker-compose restart
docker-compose restart postgres opensearch
```

### Stop All Services
```bash
docker-compose down
```

### Start All Services Again
```bash
docker-compose up -d
```

---

## 🛠️ Configuration

### .env File Location
```
c:\Users\yhvh\Documents\code\Olav\.env
```

### Key Settings
```bash
# Mode
OLAV_MODE=quicktest

# LLM (using local Ollama)
LLM_PROVIDER=ollama
LLM_MODEL_NAME=ministral-3:14b-instruct-2512-q8_0
LLM_BASE_URL=http://host.docker.internal:11434

# Embedding Model
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text:latest

# Database Access (from host)
POSTGRES_URI=postgresql://olav:olav@localhost:55432/olav
OPENSEARCH_URL=http://localhost:19200

# Device Credentials
DEVICE_USERNAME=cisco
DEVICE_PASSWORD=cisco

# Network Inventory
NETBOX_URL=http://netbox:8080
NETBOX_TOKEN=0123456789abcdef0123456789abcdef01234567
```

---

## 🔍 Workflow Examples

### Example 1: Read-Only Network Query (SuzieQ)
```bash
uv run python -m olav.cli "查询所有接口 UP 状态"
```
- **Workflow:** QueryDiagnosticWorkflow
- **Approval Required:** ❌ No
- **Data Source:** SuzieQ (Parquet files - read-only)
- **Output:** Network interface statistics

### Example 2: Device Configuration Change (NETCONF)
```bash
uv run python -m olav.cli "修改 R1 mtu 为 9000"
```
- **Workflow:** DeviceExecutionWorkflow
- **Approval Required:** ✅ Yes (HITL interrupt)
- **Data Source:** NetBox inventory
- **Action:** NETCONF/gNMI configuration
- **Logging:** Audit trail in syslog-raw index

### Example 3: Complex Multi-Step Diagnostics (Deep Dive)
```bash
uv run python -m olav.cli -e "诊断为什么 R1 和 R2 之间 BGP 无法建立邻接"
```
- **Workflow:** DeepDiveWorkflow
- **Approval Required:** ✅ Yes (for any write operations)
- **Features:**
  - Automatic task decomposition
  - Recursive diagnostics (up to 3 levels)
  - Batch audits (30+ devices in parallel)
  - Progress tracking with resume capability

### Example 4: NetBox Inventory Management
```bash
uv run python -m olav.cli "添加新路由器 R99 到 NetBox"
```
- **Workflow:** NetBoxManagementWorkflow
- **Approval Required:** ✅ Yes
- **Data Source:** NetBox API
- **Action:** Create/update/delete devices, interfaces

---

## 📊 Monitoring & Debugging

### Check OpenSearch Indices
```bash
curl http://localhost:19200/_cat/indices?v
```

### Count Documents in Index
```bash
curl -X POST http://localhost:19200/suzieq-schema/_count
```

### View PostgreSQL Checkpointer State
```bash
docker-compose exec -T postgres psql -U olav -d olav -c "SELECT * FROM checkpoints LIMIT 5;"
```

### View Syslog Audit Trail
```bash
curl -X POST http://localhost:19200/syslog-raw/_search -H 'Content-Type: application/json' -d '{"query": {"match_all": {}}, "size": 10}'
```

---

## 🧪 Testing Workflows

### Test Normal Mode Workflows
```bash
# Query diagnostics (read-only)
uv run pytest tests/unit/test_agents.py::test_query_diagnostic_workflow -v

# Device execution (with mock HITL)
uv run pytest tests/unit/test_agents.py::test_device_execution_workflow -v

# NetBox management
uv run pytest tests/unit/test_agents.py::test_netbox_management_workflow -v
```

### Test Expert Mode
```bash
# Deep Dive with task decomposition
uv run pytest tests/e2e/test_deep_dive_workflow.py -v
```

### Performance Testing
```bash
uv run pytest tests/e2e/test_performance.py -v
```

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| `INITIALIZATION_COMPLETE.md` | Detailed initialization report |
| `README.md` | Complete architecture (2300+ lines) |
| `docs/API_USAGE.md` | OLAV API documentation |
| `docs/ARCHITECTURE_EVALUATION.md` | Design decisions & trade-offs |
| `docs/KNOWN_ISSUES_AND_TODO.md` | Outstanding items |
| `.github/copilot-instructions.md` | Development guidelines |

---

## 🔧 Common Tasks

### Add New Network Device to Inventory
1. Access NetBox at http://localhost:8080
2. Click "Devices" → "Add Device"
3. Fill in device details and save
4. OLAV will discover it via the schema index

### Debug a Workflow Execution
```bash
# Check PostgreSQL state persistence
docker-compose exec -T postgres psql -U olav -d olav -c "SELECT run_id, created_at FROM checkpoints ORDER BY created_at DESC LIMIT 5;"

# View recent logs
docker-compose logs -f olav-app --tail 100

# Check OpenSearch episodic memory
curl -X POST http://localhost:19200/olav-episodic-memory/_search -H 'Content-Type: application/json' -d '{"query": {"match_all": {}}, "size": 5, "sort": [{"timestamp": "desc"}]}'
```

### Reset Initialization (Force Reinit)
```bash
# Reset specific index
uv run python -m olav.etl.init_all --openconfig --force

# Reset all indexes
uv run python -m olav.etl.init_all --force

# Reinit just PostgreSQL
uv run python -m olav.etl.init_all --postgres --force
```

---

## ⚙️ Environment Setup Reminder

Make sure you have:
1. ✅ Docker Desktop running
2. ✅ All containers healthy (`docker-compose ps`)
3. ✅ `.env` configured with local URLs
4. ✅ `uv` installed (`uv --version`)
5. ✅ Python 3.11+ available

---

## 🆘 Troubleshooting

### "Connection refused" Errors
**Issue:** Cannot connect to PostgreSQL or OpenSearch  
**Solution:** Verify `.env` has `localhost` addresses:
```bash
POSTGRES_URI=postgresql://olav:olav@localhost:55432/olav
OPENSEARCH_URL=http://localhost:19200
```

### "Table already exists" Error
**Issue:** Re-running init_postgres fails  
**Solution:** Tables are expected to exist. This is not an error. To reset:
```bash
docker-compose down -v
docker-compose up -d postgres opensearch
uv run python -m olav.etl.init_all
```

### OpenSearch "security_exception"
**Issue:** Authentication failures on OpenSearch  
**Solution:** Security is disabled in quicktest mode. Verify:
```bash
OPENSEARCH_SECURITY_DISABLED=true
```

### SuzieQ "No parquet data"
**Issue:** Queries return empty results  
**Solution:** SuzieQ needs polling to collect data. This is expected in fresh setup. Data will populate as network is monitored.

### HITL Approval Never Completes
**Issue:** Write operation hangs waiting for approval  
**Solution:** Check Docker logs for timeout:
```bash
docker-compose logs olav-app | grep -i interrupt
```

---

## 🎯 Next Steps After Initialization

1. **Test a simple query:**
   ```bash
   uv run python -m olav.cli "查询网络拓扑"
   ```

2. **Explore OpenSearch indices:**
   Visit http://localhost:19200/_cat/indices?v

3. **Check SuzieQ data:**
   Visit http://localhost:8501 (SuzieQ dashboard)

4. **Review generated documents:**
   Check `INITIALIZATION_COMPLETE.md` for detailed status

5. **Read architecture docs:**
   See `README.md` for comprehensive design overview

---

## 📞 Support

For detailed information:
- Architecture: See `README.md`
- API: See `docs/API_USAGE.md`
- Issues: See `docs/KNOWN_ISSUES_AND_TODO.md`
- Development: See `.github/copilot-instructions.md`

---

**OLAV is ready for network operations! 🚀**

Start with:
```bash
cd c:\Users\yhvh\Documents\code\Olav
uv run python -m olav.cli
```
