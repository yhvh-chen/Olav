# 从零开始完全测试清理计划 (From-Zero Reset Plan)

## 1. 清理步骤顺序 (Cleanup Sequence)

### Phase 1: Docker清理 (Docker Cleanup)
```powershell
# 停止所有容器
docker-compose down

# 移除镜像（可选，仅保留基础镜像）
docker-compose down --rmi all

# 清理未使用的Docker资源
docker system prune -a
```

### Phase 2: 本地数据清理 (Local Data Cleanup)
```powershell
# 移除持久化数据目录
Remove-Item -Path "data\*" -Recurse -Force -ErrorAction SilentlyContinue

# 移除Python编译文件（所有__pycache__目录）
Get-ChildItem -Path . -Include "__pycache__" -Recurse -Directory | Remove-Item -Recurse -Force

# 移除.pyc文件
Get-ChildItem -Path . -Include "*.pyc" -Recurse -Force | Remove-Item -Force

# 移除虚拟环境（如果使用了本地venv）
Remove-Item -Path ".venv" -Recurse -Force -ErrorAction SilentlyContinue
```

### Phase 3: 配置验证 (Config Verification)
```powershell
# 检查inventory.csv是否存在（用于测试）
Test-Path "config\inventory.csv"

# 检查setup脚本
Test-Path "setup.ps1"
Test-Path "setup.sh"

# 检查CLI入口
Test-Path "src\olav\cli\commands.py"
```

## 2. 需要删除的目录清单 (Directories to Delete)

| 目录 | 优先级 | 理由 | 命令 |
|------|--------|------|------|
| `data/` | 🔴 必删 | PostgreSQL/OpenSearch数据 | `Remove-Item data -Recurse` |
| `__pycache__/` (all) | 🔴 必删 | Python字节码缓存 | `Get-ChildItem -Include __pycache__ -Recurse \| Remove-Item -Recurse` |
| `.venv/` | 🟡 可删 | 本地虚拟环境 | `Remove-Item .venv -Recurse` |
| `*.pyc` (all) | 🔴 必删 | Python编译文件 | `Get-ChildItem -Include *.pyc -Recurse \| Remove-Item` |
| `.docker/` | 🔴 必删 | Docker compose状态 | `Remove-Item .docker -Recurse -ErrorAction SilentlyContinue` |

## 3. 需要保留的目录 (Directories to Keep)

| 目录 | 理由 |
|------|------|
| `src/` | ✅ 已修复的代码 |
| `scripts/` | ✅ 已修复的setup脚本 |
| `config/` | ✅ 配置文件（包括inventory.csv用于测试） |
| `.git/` | ✅ 版本历史 |
| `docs/` | ✅ 文档 |
| `tests/` | ✅ 测试套件 |
| `pyproject.toml` | ✅ 依赖声明 |
| `uv.lock` | ✅ 依赖锁定 |
| `docker-compose*.yml` | ✅ Docker配置 |
| `Dockerfile*` | ✅ Docker镜像定义 |
| `setup.ps1` / `setup.sh` | ✅ 初始化入口 |

## 4. 完整的清理脚本 (Complete Cleanup Script)

### PowerShell版本 (Windows)
```powershell
# 1. Docker清理
Write-Host "=== Phase 1: Docker Cleanup ===" -ForegroundColor Cyan
Write-Host "Stopping containers..." -ForegroundColor Yellow
docker-compose down --remove-orphans

Write-Host "Removing images..." -ForegroundColor Yellow
docker-compose down --rmi all -v

Write-Host "Cleaning up Docker resources..." -ForegroundColor Yellow
docker system prune -a --volumes -f

# 2. 数据清理
Write-Host "`n=== Phase 2: Data Cleanup ===" -ForegroundColor Cyan

Write-Host "Removing data directory..." -ForegroundColor Yellow
if (Test-Path "data") {
    Remove-Item -Path "data\*" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "✓ data/ cleaned" -ForegroundColor Green
}

Write-Host "Removing __pycache__ directories..." -ForegroundColor Yellow
$cacheCount = (Get-ChildItem -Path . -Include "__pycache__" -Recurse -Directory).Count
Get-ChildItem -Path . -Include "__pycache__" -Recurse -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "✓ Removed $cacheCount __pycache__ directories" -ForegroundColor Green

Write-Host "Removing .pyc files..." -ForegroundColor Yellow
$pycCount = (Get-ChildItem -Path . -Include "*.pyc" -Recurse -Force).Count
Get-ChildItem -Path . -Include "*.pyc" -Recurse -Force -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Host "✓ Removed $pycCount .pyc files" -ForegroundColor Green

Write-Host "Removing .docker directory..." -ForegroundColor Yellow
if (Test-Path ".docker") {
    Remove-Item -Path ".docker" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "✓ .docker/ removed" -ForegroundColor Green
}

Write-Host "Removing virtual environment..." -ForegroundColor Yellow
if (Test-Path ".venv") {
    Remove-Item -Path ".venv" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "✓ .venv/ removed" -ForegroundColor Green
}

# 3. 验证
Write-Host "`n=== Phase 3: Verification ===" -ForegroundColor Cyan
Write-Host "✓ setup.ps1 exists: $(Test-Path 'setup.ps1')" -ForegroundColor Green
Write-Host "✓ setup.sh exists: $(Test-Path 'setup.sh')" -ForegroundColor Green
Write-Host "✓ config exists: $(Test-Path 'config')" -ForegroundColor Green
Write-Host "✓ src exists: $(Test-Path 'src')" -ForegroundColor Green
Write-Host "✓ inventory.csv exists: $(Test-Path 'config\inventory.csv')" -ForegroundColor Green

Write-Host "`n=== 清理完成！Ready for from-zero initialization ===" -ForegroundColor Green
```

### Bash版本 (Linux/macOS)
```bash
#!/bin/bash

echo "=== Phase 1: Docker Cleanup ===" 
echo "Stopping containers..."
docker-compose down --remove-orphans

echo "Removing images..."
docker-compose down --rmi all -v

echo "Cleaning up Docker resources..."
docker system prune -a --volumes -f

echo -e "\n=== Phase 2: Data Cleanup ===" 

echo "Removing data directory..."
rm -rf data/*
echo "✓ data/ cleaned"

echo "Removing __pycache__ directories..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
echo "✓ __pycache__ directories removed"

echo "Removing .pyc files..."
find . -type f -name "*.pyc" -delete 2>/dev/null
echo "✓ .pyc files removed"

echo "Removing .docker directory..."
rm -rf .docker 2>/dev/null
echo "✓ .docker/ removed"

echo "Removing virtual environment..."
rm -rf .venv 2>/dev/null
echo "✓ .venv/ removed"

echo -e "\n=== Phase 3: Verification ===" 
echo "✓ setup.ps1 exists: $([ -f setup.ps1 ] && echo 'Yes' || echo 'No')"
echo "✓ setup.sh exists: $([ -f setup.sh ] && echo 'Yes' || echo 'No')"
echo "✓ config exists: $([ -d config ] && echo 'Yes' || echo 'No')"
echo "✓ src exists: $([ -d src ] && echo 'Yes' || echo 'No')"
echo "✓ inventory.csv exists: $([ -f config/inventory.csv ] && echo 'Yes' || echo 'No')"

echo -e "\n=== 清理完成！Ready for from-zero initialization ===" 
```

## 5. 从零开始的测试流程 (From-Zero Test Flow)

### 步骤1: 执行完整清理
```powershell
# Windows
.\cleanup_and_reset.ps1

# Linux/macOS
bash cleanup_and_reset.sh
```

### 步骤2: 验证清理结果
```powershell
# 确保data目录为空
dir data

# 确保没有Python缓存
Get-ChildItem -Include "__pycache__" -Recurse

# 确保没有容器运行
docker ps

# 确保没有镜像
docker images | grep olav
```

### 步骤3: 运行setup脚本（从零开始）
```powershell
# Windows PowerShell
.\setup.ps1

# Linux/macOS
bash setup.sh
```

### 步骤4: 验证初始化成功
```bash
# 检查PostgreSQL
docker exec olav-postgres psql -U olav -d olav -c "\dt"

# 检查OpenSearch索引
curl http://localhost:9200/_cat/indices?v | grep -E "schema|memory"

# 检查SuzieQ数据
ls -la data/suzieq-parquet/
```

## 6. 关键修复验证清单 (Key Fixes Verification)

- [ ] **Fix 1**: setup.sh - Auto CSV detection working
- [ ] **Fix 2**: setup.ps1 - No broken --csv calls
- [ ] **Fix 3**: CLI --csv parameter - Device import working
- [ ] **Fix 4**: init_all.py - Device import integrated

## 7. 故障排除 (Troubleshooting)

如果从零开始测试失败：

1. **Docker连接失败**
   ```powershell
   docker system prune -a  # 清理所有未使用资源
   docker-compose up -d    # 重新启动
   ```

2. **PostgreSQL初始化失败**
   ```powershell
   # 删除PostgreSQL数据卷
   docker volume rm olav_postgres_data
   docker-compose up -d postgres
   ```

3. **OpenSearch不可用**
   ```powershell
   # 增加可用内存
   docker-compose down
   # 编辑docker-compose.yml，增加opensearch ES_JAVA_OPTS
   docker-compose up -d
   ```

4. **CSV导入失败**
   - 检查 `config/inventory.csv` 格式
   - 检查 `NETBOX_CSV_PATH` 环境变量
   - 查看 `scripts/netbox_ingest.py` 日志

## 8. 预期输出 (Expected Output After Cleanup + Reset)

```
=== Phase 1: Docker Cleanup ===
✓ Containers stopped and removed
✓ Images removed
✓ Docker resources pruned

=== Phase 2: Data Cleanup ===
✓ data/ cleaned
✓ Removed 15 __pycache__ directories
✓ Removed 234 .pyc files
✓ .docker/ removed
✓ .venv/ removed

=== Phase 3: Verification ===
✓ setup.ps1 exists: True
✓ setup.sh exists: True
✓ config exists: True
✓ src exists: True
✓ inventory.csv exists: True

=== 清理完成！Ready for from-zero initialization ===
```

---

## 总结 (Summary)

此计划提供了完全清理Olav项目的步骤，使其回到初始状态。所有4个代码修复已在代码中，现在可以通过从零开始的初始化来验证修复是否有效。

**下一步建议：**
1. ✅ 执行此清理计划
2. ✅ 运行setup脚本（setup.ps1或setup.sh）
3. ✅ 验证所有初始化步骤正确执行
4. ✅ 检查设备是否正确导入到NetBox
