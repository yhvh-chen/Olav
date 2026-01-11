# OLAV v0.8 Phase 1 MVP - 快速开始

## 最新状态 ✅

查询问题已完全解决！Agent 现在可以：
1. 识别您在 Nornir inventory 中的设备
2. 搜索相关命令
3. 准备执行（HITL 批准前等待）

## 一分钟快速开始

```bash
# 1️⃣ 初始化能力库 (首次运行)
uv run python scripts/init_capabilities.py

# 2️⃣ 查看所有设备
uv run python -m olav devices

# 3️⃣ 查询设备信息
uv run python -m olav query "查看 R1 接口"
```

## 完整步骤

### 前置条件
- ✅ `.env` 已配置 (LLM_API_KEY, 等)
- ✅ `.olav/config/nornir/hosts.yaml` 已配置设备
- ✅ `uv sync` 已运行

### 初始化 (仅需一次)

```bash
# 加载命令白名单到 DuckDB
uv run python scripts/init_capabilities.py

# 输出:
# Loading blacklist commands from .olav\imports\commands\blacklist.txt...
# Successfully loaded 6/6 commands
# Loading cisco_ios commands from .olav\imports\commands\cisco_ios.txt...
# Successfully loaded 54/54 commands
# Total capabilities after initialization: 111
```

### 验证设置

```bash
# 显示所有配置
uv run python -m olav config

# 输出应该显示:
# LLM Provider: openai
# LLM Model: x-ai/grok-4.1-fast
# Device Username: cisco
```

### 查看设备

```bash
uv run python -m olav devices

# 输出:
# Available devices:
# - R1 (192.168.100.101) - cisco_ios - border@lab
# - R2 (192.168.100.102) - cisco_ios - border@lab
# - R3 (192.168.100.103) - cisco_ios - core@lab
# ... (更多设备)
```

### 执行查询

```bash
# 中文查询
uv run python -m olav query "查看 R1 接口"
uv run python -m olav query "列出所有 BGP 邻接"
uv run python -m olav query "核心路由器的 CPU 使用率"

# 英文查询
uv run python -m olav query "Show all interfaces on R1"
uv run python -m olav query "List BGP neighbors"

# 带调试输出
uv run python -m olav query "查看 R1 接口" --debug
```

## 预期输出示例

```bash
$ uv run python -m olav query "查看 R1 接口"

┌─────────────────────────────────┐
│ Query: 查看 R1 接口              │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ Response: Available devices:     │
│ - R1 (192.168.100.101) - c...   │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ Response: Found 9 capabilities:  │
│ 1. show interface* (cisco_ios)   │
│ 2. show ip interface brief ...   │
└─────────────────────────────────┘

⏸️  HITL Interrupt: Awaiting approval for:
    - nornir_execute(R1, "show ip interface brief")
    - nornir_execute(R1, "show interfaces status")
    - nornir_execute(R1, "show interfaces")
```

## 问题排查

### 问题: "No devices found"
```bash
# 检查 hosts.yaml 格式
cat .olav/config/nornir/hosts.yaml

# 格式应该是 (NO 顶层 'hosts:' key):
# R1:
#   hostname: 192.168.100.101
#   platform: cisco_ios
```

### 问题: "No capabilities found"
```bash
# 运行初始化脚本
uv run python scripts/init_capabilities.py

# 检查文件存在
ls -la .olav/imports/commands/
```

### 问题: "ModuleNotFoundError"
```bash
# 重新同步依赖
uv sync

# 清除缓存
rm -rf .venv/__pycache__ .olav/capabilities.db
```

## 文件位置参考

| 文件 | 用途 |
|------|------|
| `.env` | LLM API 密钥和设备凭证 |
| `.olav/config/nornir/hosts.yaml` | Nornir 设备清单 |
| `.olav/config/nornir/groups.yaml` | 设备分组 |
| `.olav/imports/commands/*.txt` | 命令白名单 |
| `.olav/capabilities.db` | DuckDB 能力库 |
| `src/olav/cli.py` | CLI 实现 |
| `src/olav/agent.py` | Agent 核心逻辑 |

## 常用命令速查

```bash
# 列出所有命令
uv run python -m olav --help

# 交互模式
uv run python -m olav interactive

# 显示版本
uv run python -m olav version

# 查看配置
uv run python -m olav config

# 列出设备
uv run python -m olav devices

# 查询
uv run python -m olav query "YOUR_QUERY_HERE"

# 查询 + 调试
uv run python -m olav query "YOUR_QUERY_HERE" --debug
```

## 下一步 (Phase 2+)

- [ ] HITL 批准端点实现
- [ ] SSH/NETCONF 连接到真实设备
- [ ] 命令输出解析
- [ ] 深度分析技能
- [ ] 自动化修复建议

## 参考文档

- [CLI 用户指南](CLI_USER_GUIDE.md) - 详细的 CLI 命令文档
- [Nornir 修复分析](NORNIR_FIX_ANALYSIS.md) - 问题根本原因和修复说明
- [配置权威](CONFIG_AUTHORITY.md) - 配置文件优先级
- [设计文档](DESIGN_V0.8.md) - 完整设计和路线图

## 获取帮助

```bash
# 运行测试
uv run pytest tests/ -v

# 查看日志
tail -f .olav/logs/*.log

# 检查数据库
uv run python -c "from olav.core.database import get_database; db = get_database(); print(db.search_capabilities('interface'))"
```

---

**Status**: ✅ Phase 1 MVP Complete
**Last Updated**: 2026-01-07
**Next Milestone**: Phase 2 - Deep Analysis Skills
