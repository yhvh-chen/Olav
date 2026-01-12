# v0.8.1 Unified Data Layer - 开发指南

## 🎯 项目状态

- **分支**: `feature/v0.8.1-unified-data-layer` (Gitea 仅)
- **提交**: 7c6c10f - 初始架构和设计文档
- **设计文档**: `docs/0.md` (1405 行，完整设计)
- **计划**: 26h 开发 + 测试

## 📋 项目概览

### 目标
合并 Topology + Backup + Inspect 为统一离线数据层，支持 Workflow 编排

### 核心创新
- **Map-Reduce 模式**: 50K tokens → 500 tokens (上下文减少 100 倍)
- **每设备×每命令粒度**: 精准异常检测，避免幻觉
- **动态能力查询**: 多厂商支持，无硬编码命令

## 🔧 环境要求

```bash
# 1. 确认分支
git branch
# 应该显示: * feature/v0.8.1-unified-data-layer

# 2. 验证 uv 环境
uv --version

# 3. 安装依赖 (如需要)
uv sync

# 4. 验证配置
# - .env 中有 LLM API Key
# - hosts.yml 中有设备定义
```

## 📝 设计文档结构

| Section | 内容 | 核心 |
|---------|------|------|
| 1 | 架构概览 | 5 阶段流水线 + Map-Reduce 模式 |
| 2 | 数据结构 | 目录布局、JSON 格式、DuckDB Schema |
| 3 | DuckDB Schema | 同步表 + 检查表 + 日志表 |
| 4 | Workflow | daily-run.md 定义 |
| 5 | Skills | daily-sync, inspect-analyzer, log-analyzer, daily-report |
| 6 | Tools | sync_tools, event_tools, map_tools, llm_interface, map_scheduler |
| 7 | Commands | /sync, /daily-run, /logs 实现 |
| 8-10 | 支持与设计 | 跨平台、决策、不做事项 |
| 11 | 开发计划 | 26h 分 11 个 Phase |
| 12 | 验收标准 | 功能、性能、质量检查清单 |
| **13** | **开发注意事项** | **配置、代码清理、测试、分支策略** |

## 🚀 开发顺序

### Phase 1-5: 基础工具层 (8h)
- [ ] sync_tools.py - 数据采集、搜索、diff、SQL 查询
- [ ] 存储结构与归档
- [ ] event_tools.py - 日志解析、事件查询
- [ ] 查询工具整合
- [ ] 拓扑生成

### Phase 6-7: LLM 层 (4h)
- [ ] llm_interface.py - MapReduceLLM 类
- [ ] map_scheduler.py - 并发调度、错误处理
- [ ] map_tools.py - 聚合函数

### Phase 8-9: Skill 层 (5h)
- [ ] inspect-analyzer (L1-L4 检查)
- [ ] log-analyzer (关键词触发)
- [ ] daily-report (Reduce 汇总)

### Phase 10-11: 集成与测试 (4h)
- [ ] 错误处理与降级报告
- [ ] Unit 测试 (所有新函数)
- [ ] E2E 测试 (真实 LLM + 设备)

## 📊 文件清单

### 新增文件 (核心)

| Phase | 文件 | 行数 | 说明 |
|-------|------|------|------|
| 1 | `src/olav/tools/sync_tools.py` | ~300 | 数据采集工具 |
| 2 | 目录结构 | - | data/sync/{date}/{raw,parsed,map,reports}/ |
| 3 | `src/olav/tools/event_tools.py` | ~200 | 日志解析工具 |
| 4 | SQL 查询工具 | ~100 | 集成到 sync_tools |
| 5 | `src/olav/tools/topology_tools.py` | ~200 | 拓扑生成 (已有) |
| **6** | **`src/olav/core/llm_interface.py`** | **~150** | **MapReduceLLM 类** |
| **6** | **`src/olav/core/map_scheduler.py`** | **~200** | **调度和错误处理** |
| **7** | **`src/olav/tools/map_tools.py`** | **~100** | **聚合函数** |
| 8 | `.olav/skills/daily-sync/SKILL.md` | ~50 | 采集定义 |
| 8 | `.olav/skills/inspect-analyzer/SKILL.md` | ~150 | L1-L4 检查 |
| 9 | `.olav/skills/log-analyzer/SKILL.md` | ~150 | 关键词触发 |
| 9 | `.olav/skills/daily-report/SKILL.md` | ~120 | Reduce 报告 |
| 10 | `.olav/workflows/daily-run.md` | ~100 | 流水线定义 |

### 修改文件

| 文件 | 改动 | 说明 |
|------|------|------|
| `src/olav/tools/inspection_tools.py` | collect_inspection_data() | 改为只收集，不判断 |
| `pyproject.toml` | dependencies | 补充 asyncio, asyncpg (如需) |
| `.olav/imports/commands/` | 检查白名单 | 添加新的 intent (如需) |

## ✅ 代码质量要求

### 必须通过

```bash
# 1. 代码格式化
uv run ruff format .

# 2. 代码检查
uv run ruff check .

# 3. 类型检查
uv run pyright

# 4. 单元测试
uv run pytest tests/ -v

# 5. 代码覆盖
uv run pytest tests/ --cov=src/olav --cov-report=html
```

### 代码标准

- ✅ 所有函数有 type hints
- ✅ 所有公开函数有 docstrings
- ✅ 无 ghost code / 垃圾代码
- ✅ 测试覆盖 > 80%

### 测试要求

**Unit 测试** (必须)
```bash
tests/test_sync_tools.py
tests/test_event_tools.py
tests/test_map_tools.py
tests/test_map_scheduler.py
```

**E2E 测试** (必须使用真实环境)
```bash
tests/e2e/test_daily_run.py
# - 真实 LLM API (非 mock)
# - 真实设备连接 (非模拟数据)
# - 手动验证输出质量
```

## 🔐 配置使用

### LLM 配置 (.env 复用)

```bash
# 已定义，直接使用
ANTHROPIC_API_KEY=sk-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# Python 代码中使用
from config.settings import get_llm_config
llm_config = get_llm_config()
```

### 设备配置 (hosts.yml 复用)

```bash
# hosts.yml 已定义设备列表
# Python 代码中使用
from src.olav.tools.network import get_nornir_inventory
inventory = get_nornir_inventory()
```

## 🌳 分支管理

### 重要: 仅在 Gitea 开发

```bash
# ✅ 允许
git push gitea feature/v0.8.1-unified-data-layer
git push gitea main (完成后)

# ❌ 禁止
git push origin feature/v0.8.1-unified-data-layer
git push origin main (除非特殊情况)
```

### 提交消息格式

```bash
# 参考现有提交
feat: 新功能描述
  - 详细说明
  - 多行说明

fix: Bug 修复描述

docs: 文档更新

test: 测试相关
```

## 📞 联系信息

- **设计文档**: `docs/0.md`
- **开发指南**: `DEVELOPMENT_v0.8.1.md` (本文件)
- **分支**: `feature/v0.8.1-unified-data-layer` (Gitea)

## 🎯 下一步

1. ✅ 已完成: 创建分支并提交设计文档
2. 🔲 开始 Phase 1: 实现 sync_tools.py
3. 🔲 每个 Phase 完成后在 Gitea 提交
4. 🔲 完成所有 Phase 后合并到 main

---

**开发开始日期**: 2026-01-13  
**预计完成**: 2026-01-17 (26h 开发)  
**状态**: 🟡 设计完成，等待开发开始
