# ⚡ OLAV 快速参考卡片 (Quick Reference Card)

## 🎯 核心命令速查表 (Command Quick Reference)

### 清理和重置 (Cleanup & Reset)
```powershell
# Windows PowerShell
.\cleanup_and_reset.ps1          # 完整清理 (完全重置)
docker-compose down               # 仅停止容器
docker-compose down --rmi all    # 停止容器并删除镜像
docker volume prune -a            # 删除所有数据卷
```

```bash
# Linux/macOS
bash cleanup_and_reset.sh         # 完整清理
docker-compose down
docker-compose down --rmi all
docker volume prune -a
```

### 初始化 (Initialization)
```powershell
# Windows
.\setup.ps1                       # 完整初始化
uv sync                           # 安装Python依赖
docker-compose up -d              # 启动容器
```

```bash
# Linux/macOS
bash setup.sh                     # 完整初始化
uv sync                           # 安装Python依赖
docker-compose up -d              # 启动容器
```

### 验证 (Verification)
```bash
# 检查容器
docker ps

# 检查PostgreSQL
docker exec olav-postgres psql -U olav -d olav -c "\dt"

# 检查OpenSearch
curl http://localhost:9200/_cat/indices?v

# 检查设备导入
curl -s http://localhost:8000/api/dcim/devices/ | jq '.count'

# 检查SuzieQ数据
ls -la data/suzieq-parquet/
```

---

## 📋 5分钟快速部署 (5-Minute Quick Deploy)

### 场景1: 从零开始
```bash
# 1. 进入项目目录
cd ~/code/Olav

# 2. 运行清理脚本（可选，但推荐）
bash cleanup_and_reset.sh

# 3. 运行初始化脚本
bash setup.sh

# 4. 等待10-15秒后验证
docker ps                          # 应该看到所有容器运行中
curl http://localhost:9200         # OpenSearch就绪
curl http://localhost:8000         # NetBox就绪
```

### 场景2: 快速重启
```bash
# 仅重启Docker容器（保留数据）
docker-compose restart

# 验证
docker ps
```

### 场景3: 清理坏数据
```bash
# 删除持久化数据但保留容器
docker-compose down -v

# 重新启动
docker-compose up -d

# 重新初始化
uv run python -m olav.etl.init_all
```

---

## 🔍 常见问题速解 (FAQ Quick Fixes)

| 问题 | 症状 | 解决 |
|------|------|------|
| 容器崩溃 | `docker ps` 只显示部分 | `docker-compose logs <container>` 查看日志 |
| PostgreSQL连接失败 | "FATAL: database does not exist" | `docker volume rm olav_postgres_data && docker-compose up -d postgres` |
| OpenSearch OOM | Container退出 | 增加Docker内存或修改docker-compose.yml中的`ES_JAVA_OPTS` |
| CSV导入失败 | "Device import failed" | 检查 `config/inventory.csv` 格式，查看 `docker logs olav-app` |
| 端口冲突 | "Address already in use" | `lsof -i :8000` (Mac) / `netstat -ano \| findstr :8000` (Windows) 找出占用程序 |

---

## 📂 关键文件位置 (Key File Locations)

| 用途 | 文件 | 行动 |
|------|------|------|
| 初始化脚本 | `setup.ps1` / `setup.sh` | 运行来初始化系统 |
| 清理脚本 | `cleanup_and_reset.ps1` / `.sh` | 运行来重置系统 |
| 配置 | `config/olav.yaml` | 编辑来修改设置 |
| Docker | `docker-compose.yml` | 编辑来修改容器配置 |
| 测试数据 | `config/inventory.csv` | 编辑来修改测试设备 |
| 源代码 | `src/olav/` | 编辑来修改功能 |
| 日志 | `docker logs <container>` | 查看来调试问题 |

---

## 🔄 初始化流程图 (Initialization Flow)

```
start
  │
  ├─→ 验证系统要求 (Check Docker, Python, uv)
  │     └─→ ✓ 通过
  │
  ├─→ 启动Docker容器 (docker-compose up -d)
  │     ├─→ PostgreSQL (port 5432)
  │     ├─→ OpenSearch (port 9200)
  │     ├─→ Redis (port 6379)
  │     ├─→ NetBox (port 8000)
  │     └─→ SuzieQ (port 8088)
  │
  ├─→ 初始化PostgreSQL (CheckPointer tables)
  │     └─→ ✓ LangGraph状态保存
  │
  ├─→ 初始化OpenConfig YANG Schema
  │     └─→ ✓ XPath索引建立
  │
  ├─→ 初始化SuzieQ Schema
  │     └─→ ✓ Table定义加载
  │
  ├─→ ✅ 导入设备到NetBox (NEW!)
  │     └─→ 从 config/inventory.csv 导入
  │
  └─→ 完成！(Ready for operations)
       └─→ OLAV应用就绪
```

---

## 📊 系统健康检查 (System Health Check)

```bash
#!/bin/bash
# 运行此脚本检查系统状态

echo "🔍 Checking OLAV System Health..."
echo ""

# 1. Docker
echo "1️⃣  Docker Containers:"
docker ps --format "table {{.Names}}\t{{.Status}}"

# 2. PostgreSQL
echo ""
echo "2️⃣  PostgreSQL Checkpointer Tables:"
docker exec olav-postgres psql -U olav -d olav -c "SELECT tablename FROM pg_tables WHERE schemaname='public';" 2>/dev/null || echo "❌ PostgreSQL not accessible"

# 3. OpenSearch
echo ""
echo "3️⃣  OpenSearch Indices:"
curl -s http://localhost:9200/_cat/indices?v 2>/dev/null | head -5 || echo "❌ OpenSearch not accessible"

# 4. NetBox
echo ""
echo "4️⃣  NetBox API:"
curl -s http://localhost:8000/api/ 2>/dev/null | jq '.users' || echo "❌ NetBox not accessible"

# 5. Devices
echo ""
echo "5️⃣  Imported Devices:"
curl -s http://localhost:8000/api/dcim/devices/ 2>/dev/null | jq '.count' || echo "❌ Device API not accessible"

# 6. Files
echo ""
echo "6️⃣  Critical Files:"
echo "  setup.ps1: $([ -f setup.ps1 ] && echo '✓' || echo '✗')"
echo "  setup.sh: $([ -f setup.sh ] && echo '✓' || echo '✗')"
echo "  config/inventory.csv: $([ -f config/inventory.csv ] && echo '✓' || echo '✗')"
echo "  src/olav/cli/commands.py: $([ -f src/olav/cli/commands.py ] && echo '✓' || echo '✗')"

echo ""
echo "✅ Health check complete!"
```

---

## 🚀 部署前检查清单 (Pre-Deployment Checklist)

- [ ] Docker已安装 (`docker --version`)
- [ ] Python 3.11+ 已安装 (`python --version`)
- [ ] uv已安装 (`uv --version`)
- [ ] 至少有10GB磁盘空间
- [ ] 至少有4GB可用RAM（建议8GB）
- [ ] 端口8000, 5432, 9200, 6379未被占用
- [ ] `config/inventory.csv` 存在且格式正确
- [ ] `setup.ps1` 和 `setup.sh` 都存在
- [ ] `.git/` 目录存在（版本控制）

---

## 🎓 学习资源 (Learning Resources)

| 主题 | 文件 | 备注 |
|------|------|------|
| 完整清理说明 | `CLEANUP_AND_RESET_PLAN.md` | 详细的清理步骤和故障排除 |
| 部署总结 | `DEPLOYMENT_SUMMARY.md` | 4个修复的详细说明 |
| 快速开始 | `QUICKSTART.md` | 用户指南 |
| 架构说明 | `.github/copilot-instructions.md` | 系统设计和最佳实践 |
| API文档 | `docs/API_USAGE.md` | REST API使用说明 |

---

## 🆘 紧急求助 (Emergency Help)

### 容器全部崩溃
```bash
# 核弹选项：完全重置
docker system prune -a --volumes
docker-compose down -v
bash cleanup_and_reset.sh
bash setup.sh
```

### 只删除数据
```bash
# 保留容器，删除数据卷
docker-compose down -v
docker-compose up -d

# 重新初始化数据
uv run python -m olav.etl.init_all
```

### 只重启一个容器
```bash
# 重启PostgreSQL
docker-compose restart postgres

# 重启OpenSearch
docker-compose restart opensearch

# 查看日志
docker-compose logs -f postgres
```

---

**💡 提示**: 保存此文件到书签或打印出来便于快速参考！

**最后更新**: 2024
**状态**: ✅ Production Ready
