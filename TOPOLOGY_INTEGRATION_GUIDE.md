# 🔗 TopologyImporter 集成到 Sync 流程

## 快速开始

### 方案 A: Sync 中直接集成（推荐）

**文件**: `src/olav/cli/sync_integration.py`

```python
"""
在 Sync 流程中集成拓扑发现。

流程:
  1. Sync 完成 TextFSM 解析，生成 JSON
  2. TopologyImporter 读取这些 JSON
  3. Pydantic 验证数据完整性
  4. 写入数据库
"""

from pathlib import Path
from src.olav.tools.topology_importer import TopologyImporter


def integrate_topology_discovery(sync_dir: Path | str, db_path: Path | str) -> dict:
    """
    在 sync 流程中集成拓扑发现。
    
    Args:
        sync_dir: Sync 数据目录 (含 parsed/*.json)
        db_path: DuckDB 数据库路径
        
    Returns:
        导入结果统计
        
    Example:
        >>> result = integrate_topology_discovery(
        ...     'data/sync/2026-01-13',
        ...     '.olav/data/topology.db'
        ... )
        >>> print(f"导入 {result['valid']} 条有效链接")
    """
    importer = TopologyImporter(str(db_path))
    
    try:
        print(f"📍 开始拓扑发现导入: {sync_dir}")
        
        # 运行导入
        importer.import_from_parsed_json(str(sync_dir))
        
        # 获取统计信息
        stats = importer.get_import_stats()
        
        # 提交数据库
        importer.commit()
        
        print(f"✅ 导入完成: {stats['valid']} 条有效链接")
        
        return {
            "success": True,
            "valid": stats['valid'],
            "invalid": stats['invalid'],
            "skipped": stats['skipped'],
        }
        
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        importer.rollback()
        
        return {
            "success": False,
            "error": str(e),
        }
        
    finally:
        importer.close()


# 集成点 1: Sync 完成后执行
def run_after_sync():
    """在主 sync 流程完成后执行拓扑发现"""
    from pathlib import Path
    
    sync_dir = Path("data/sync") / "2026-01-13"
    db_path = Path(".olav/data/topology.db")
    
    return integrate_topology_discovery(sync_dir, db_path)


# 集成点 2: 支持命令行
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="拓扑发现导入")
    parser.add_argument("--sync-dir", required=True, help="Sync 数据目录")
    parser.add_argument("--db", required=True, help="数据库路径")
    
    args = parser.parse_args()
    
    result = integrate_topology_discovery(args.sync_dir, args.db)
    
    if result["success"]:
        print(f"\n✅ 成功: {result['valid']} 条有效链接")
    else:
        print(f"\n❌ 失败: {result['error']}")
        exit(1)
```

---

## 集成步骤

### Step 1: 识别 Sync 完成点

**文件**: `src/olav/cli/sync.py` 或等价文件

```python
# 在 sync 完成后
async def main():
    # ... 现有 sync 代码 ...
    
    # 步骤 1: 运行 Sync (TextFSM 解析)
    await run_sync()
    
    # 步骤 2: 运行拓扑发现 (新增)
    from sync_integration import integrate_topology_discovery
    result = integrate_topology_discovery(
        'data/sync/2026-01-13',
        '.olav/data/topology.db'
    )
    
    if not result['success']:
        logger.error(f"拓扑发现失败: {result['error']}")
```

### Step 2: 配置默认路径

**文件**: `config/settings.py`

```python
# 拓扑发现配置
TOPOLOGY = {
    "enabled": True,  # 启用拓扑发现
    "db_path": ".olav/data/topology.db",
    "sync_dir": "data/sync",
    "auto_import": True,  # sync 完成后自动导入
    "protocols": ["CDP", "LLDP", "BGP"],  # 支持的协议
}
```

### Step 3: 添加错误处理

```python
def run_with_fallback():
    """带重试和回滚的拓扑发现"""
    from pathlib import Path
    import time
    
    sync_dir = Path("data/sync/2026-01-13")
    db_path = Path(".olav/data/topology.db")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            result = integrate_topology_discovery(sync_dir, db_path)
            if result['success']:
                return result
        except Exception as e:
            logger.warning(f"尝试 {attempt+1}/{max_retries} 失败: {e}")
            time.sleep(2 ** attempt)  # 指数退避
    
    logger.error("拓扑发现失败，所有重试都已用尽")
    return {"success": False, "error": "Max retries exceeded"}
```

---

## 数据流示例

```
📊 Sync 流程 + 拓扑发现集成

┌─────────────────────────────────────────────────────────────┐
│                  Sync 执行流程                                │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────┐
        │  1. 收集原始数据 (Raw Output)      │
        │     例: "show cdp neighbors"       │
        └─────────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────┐
        │  2. TextFSM 解析                    │
        │     输出: JSON (parsed/*.json)     │
        └─────────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────┐
        │  3. 拓扑发现导入 (新增)            │  <── 这里
        │     TopologyImporter                │
        └─────────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────┐
        │  4. Pydantic 验证                   │
        │     - 检查必要字段                  │
        │     - 验证设备存在                  │
        │     - 拒绝无效数据                  │
        └─────────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────┐
        │  5. DuckDB 存储                     │
        │     topology_links 表                │
        └─────────────────────────────────────┘
                           │
                           ▼
                    ✅ 完成
```

---

## 测试集成

### 本地测试

```bash
# 1. 准备测试数据
cd /home/yhvh/Olav
python e2e_test.py  # 备份 + 清空 + 恢复

# 2. 运行集成
python -c "
from src.olav.cli.sync_integration import integrate_topology_discovery
result = integrate_topology_discovery('data/sync/2026-01-13', '.olav/data/topology.db')
print(f'结果: {result}')
"

# 3. 验证数据
duckdb -query "SELECT COUNT(*) as links FROM .olav/data/topology.db.topology_links"
```

### CI/CD 集成

```yaml
# .github/workflows/topology-test.yml
name: Topology Discovery Test

on:
  push:
    branches: [main]
    paths:
      - 'src/olav/tools/topology_importer.py'
      - 'src/olav/cli/sync_integration.py'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v2
      
      - name: 运行 E2E 测试
        run: |
          uv run python e2e_test.py
          
      - name: 验证数据
        run: |
          duckdb .olav/data/topology.db "
            SELECT COUNT(*) as links FROM topology_links
          "
```

---

## 故障排查

### 问题 1: "Unknown device" 错误

**原因**: 设备表中不存在该设备名称

**解决方案**:
```python
# 检查设备是否存在
import duckdb
conn = duckdb.connect('.olav/data/topology.db')
devices = conn.execute(
    "SELECT name FROM topology_devices"
).fetchall()
print(f"已知设备: {devices}")
```

### 问题 2: 导入 0 条链接

**原因**: TextFSM 规则无法解析该命令输出

**解决方案**:
1. 检查 TextFSM 规则是否支持该命令
2. 检查 JSON 数据是否包含邻接信息
3. 启用 LLM 备选 (可选)

```bash
# 检查 JSON 数据
cat data/sync/2026-01-13/parsed/R1/*.json | jq '.neighbors' | head -20
```

### 问题 3: 导入速度慢

**优化**:
```python
# 批量导入而不是逐条提交
importer = TopologyImporter(db_path)

for device in devices:
    importer.process_device(device)  # 不立即提交

importer.commit()  # 一次性提交全部
```

---

## 配置示例

### 最小配置

```python
# 只需这些就能工作
from pathlib import Path
from src.olav.tools.topology_importer import TopologyImporter

sync_dir = Path("data/sync/2026-01-13")
db_path = Path(".olav/data/topology.db")

importer = TopologyImporter(str(db_path))
importer.import_from_parsed_json(str(sync_dir))
importer.commit()
importer.close()
```

### 完整配置

```python
from pathlib import Path
from src.olav.tools.topology_importer import TopologyImporter
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 配置
config = {
    "db_path": ".olav/data/topology.db",
    "sync_dir": "data/sync/2026-01-13",
    "max_retries": 3,
    "timeout": 300,
    "log_level": "INFO",
}

try:
    importer = TopologyImporter(config["db_path"])
    importer.import_from_parsed_json(config["sync_dir"])
    
    stats = importer.get_import_stats()
    logger.info(f"导入成功: {stats['valid']} 条有效")
    
    importer.commit()
    
except Exception as e:
    logger.error(f"导入失败: {e}")
    importer.rollback()
    
finally:
    importer.close()
```

---

## 参考

- **TopologyImporter**: `src/olav/tools/topology_importer.py`
- **Pydantic 模型**: `src/olav/tools/topology_importer.py` → `TopologyLink`
- **E2E 测试**: `e2e_test.py`
- **架构文档**: `ARCHITECTURE_REVISION_TEXTFSM_ONLY.txt`

---

**最后更新**: 2026-01-13
