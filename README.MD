# 🤖 OLAV - 网络运维智能助手

**版本**: 0.8.0  
**状态**: ✅ Phase 1-5 完全可用  
**架构**: DeepAgents Native + 三层知识架构 (Skills/Knowledge/Tools)  
**平台**: 兼容 Claude Code, 支持 Windows/Mac/Linux

---

## 📋 目录

- [快速开始](#快速开始)
- [功能概览](#功能概览)
- [发展阶段](#发展阶段)
- [安装](#安装)
- [使用示例](#使用示例)
- [架构设计](#架构设计)
- [核心技术](#核心技术)

---

## 快速开始

### 1️⃣ 环境配置 (5 分钟)

```bash
# 安装依赖 (使用 uv - 快速包管理)
uv sync --dev

# 复制环境配置
cp .env.example .env
# 编辑 .env，添加你的设备信息和API密钥
```

### 2️⃣ 运行第一条命令

```bash
# 查询设备状态
uv run python -m olav.main "查询 R1 接口状态"

# 执行全面巡检
uv run python -m olav.main "inspect all lab devices"

# 搜索能力库
uv run python -m olav.main "如何检查BGP邻居？"
```

### 3️⃣ 在 Claude Code 中使用

```
1. 进入项目目录
2. 在 Claude Code 中打开
3. 使用 `/skills/device-inspection` 查看可用skills
4. 发送指令: "Inspect all lab devices with full L1-L4 health check"
```

---

## 功能概览

### 🎯 三大核心能力

#### 1. **Device Inspection** - 全面设备巡检
- **L1 物理层**: CPU/内存/温度/电源/风扇
- **L2 数据链路**: VLAN/STP/LLDP/MAC表
- **L3 网络层**: 路由/OSPF/BGP/VPNv4
- **L4 传输层**: TCP/进程/内存/错误计数

```bash
# 巡检所有lab设备 (自动生成HTML报告)
uv run pytest tests/e2e/test_phase5_comprehensive_l1l4.py -v
```

#### 2. **Quick Query** - 快速查询
- 1-2 个命令快速响应
- 自动命令选择
- 面向多品牌网络设备 (Cisco/Huawei/Arista)

```bash
"Check R1 CPU usage"
"Show interface status on S1"
"Get BGP neighbors from R2"
```

#### 3. **Deep Analysis** - 深度分析
- 多步骤复杂诊断
- 自动问题定位
- 提供修复建议

```bash
"Diagnose why R1 BGP neighbors are down"
"Analyze interface error rates on core switches"
"Check network security baseline compliance"
```

---

## 发展阶段

OLAV 按照 5 个阶段递进式开发，每个阶段都是完整可用的：

### Phase 1: MVP (基础框架) ✅
- **DeepAgents Agent** 基础
- **Skill 路由系统** 
- **基础命令执行** (Nornir)
- **知识库** (aliases/topology)
- **状态**: ✅ 生产可用

### Phase 2: Skill 系统 ✅
- **Skill-based routing** - LLM 智能路由
- **英文/中文支持** - 双语识别
- **三层知识架构** - Skills/Knowledge/Tools
- **多设备支持** - 自动批处理
- **状态**: ✅ 生产可用

### Phase 3: SubAgent 框架 ✅
- **Macro 分析** - 拓扑级路径分析
- **Micro 诊断** - 设备级分层诊断
- **后向兼容** - 保留原有skills
- **自动降级** - 无法访问时优雅处理
- **状态**: ✅ 生产可用

### Phase 4: 检查自动化 ✅
- **Comprehensive Inspection** - L1-L4 全覆盖
- **Multi-device Reports** - 统一多设备报告
- **Anomaly Detection** - 自动异常标记
- **HTML 报告生成** - 专业可视化输出
- **状态**: ✅ 生产可用

### Phase 5: 真实设备测试 ✅
- **Real Nornir 集成** - 实际设备连接
- **Real LLM API** - 真实 LLM 调用
- **完整 E2E 测试** - 16+ 真实场景
- **DuckDB 能力库** - CLI/API/NETCONF 命令库
- **状态**: ✅ 生产可用

---

## 安装

### 前置要求

- **Python 3.11+** (推荐 3.13)
- **uv** 包管理器 (快速安装: `pip install uv`)
- **网络设备** (Cisco IOS/XE, Huawei, Arista 等)
- **SSH 访问** 到网络设备

### 完整安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/OLAV.git
cd OLAV

# 2. 安装依赖
uv sync --dev

# 3. 配置环境
cp .env.example .env
# 编辑 .env:
# - DEVICE_USERNAME=admin
# - DEVICE_PASSWORD=password
# - OPENAI_API_KEY=sk-...

# 4. 配置 Nornir (网络设备库存)
# 编辑 .olav/config/nornir/hosts.yaml
# 编辑 .olav/config/nornir/groups.yaml

# 5. 验证安装
uv run pytest tests/e2e/test_phase5_comprehensive_l1l4.py::TestScopeParsingForLabInspection -v

# 预期输出: 2 passed in ~1.4s ✅
```

---

## 使用示例

### 示例 1: 基础设备查询

```python
# 方式 A: CLI
$ uv run python -m olav.main "R1 interface status"

# 预期结果:
# R1 Gi0/1: UP, 1000Mbps
# R1 Gi0/2: UP, 1000Mbps
# R1 Gi0/3: DOWN
```

### 示例 2: 全面设备巡检

```bash
# 对所有 lab 设备执行 L1-L4 全面巡检
uv run pytest tests/e2e/test_phase5_comprehensive_l1l4.py::TestComprehensiveL1L4LabInspection -v -s

# 生成的报告:
# .olav/reports/lab-comprehensive-l1l4-20260108-143000.html
#   ├─ Executive Summary (所有8个设备的整体状态)
#   ├─ L1-L4 分层数据
#   ├─ 异常检测和标记
#   └─ 修复建议
```

### 示例 3: 运行所有测试

```bash
# 单元测试
uv run pytest tests/unit/ -v

# E2E 测试
uv run pytest tests/e2e/ -v

# 覆盖率报告
uv run pytest --cov=src/olav --cov-report=html

# 代码质量检查
uv run ruff check src/
uv run ruff format src/  # 自动格式化
```

### 示例 4: 在 Claude Code 中使用

```
Claude Code 提示词:

"使用 OLAV skills 执行以下任务:
1. 使用 device-inspection skill 巡检所有 lab 设备
2. 生成综合健康报告
3. 标记任何异常
4. 提供修复建议"

预期结果:
✅ Agent 自动匹配 device-inspection skill
✅ 列举所有 lab 组设备
✅ 执行 L1-L4 巡检
✅ 生成 HTML 报告到 .olav/reports/
✅ 提取异常并建议修复
```

---

## 架构设计

### 三层知识架构

```
┌────────────────────────────────────────────────────────┐
│              OLAV 三层知识架构                          │
├────────────────────────────────────────────────────────┤
│                                                        │
│  Layer 1: SKILLS (.olav/skills/*.md)                  │
│  ├─ device-inspection    → 全面 L1-L4 巡检           │
│  ├─ quick-query          → 快速 1-2 命令查询          │
│  └─ deep-analysis        → 多步复杂诊断               │
│     [策略层 - HOW: 如何执行任务]                       │
│                                                        │
│  Layer 2: KNOWLEDGE (.olav/knowledge/*.md)            │
│  ├─ aliases.md           → 设备别名映射               │
│  ├─ topology.md          → 网络拓扑                    │
│  └─ platform-commands.md → 多品牌命令库               │
│     [知识层 - WHAT: 什么是事实]                        │
│                                                        │
│  Layer 3: TOOLS/CAPABILITIES                          │
│  ├─ Nornir               → SSH 批量执行               │
│  ├─ DuckDB              → CLI/API/NETCONF 命令库      │
│  ├─ Jinja2              → 报告模板生成               │
│  └─ LangChain           → LLM 集成                     │
│     [能力层 - CAN: 能做什么]                           │
│                                                        │
└────────────────────────────────────────────────────────┘
```

### 执行流程

```
用户输入
  ↓
┌─────────────────────────┐
│ LLM Skill Router        │
│ (意图识别 + 路由)        │
└──────────┬──────────────┘
           ↓
      选择 Skill
           ↓
┌──────────────────────────┐
│ Skill 执行引擎            │
│ (解析范围 + 执行命令)     │
└──────────┬───────────────┘
           ↓
    Nornir 批量执行
           ↓
┌──────────────────────────┐
│ 报告生成                  │
│ (Jinja2 模板 + HTML)      │
└──────────┬───────────────┘
           ↓
      输出到用户
```

---

## 核心技术

### 技术栈

| 组件 | 技术 | 用途 |
|------|------|------|
| **框架** | DeepAgents | Agent 编排和 HITL |
| **LLM** | OpenAI/Claude | 意图识别和路由 |
| **网络** | Nornir 3.3 | 多设备批量执行 |
| **数据库** | DuckDB 0.8 | 轻量能力库存储 |
| **模板** | Jinja2 3.1 | HTML 报告生成 |
| **测试** | Pytest 9.0 | 完整 E2E 测试 |
| **包管理** | uv | 快速依赖管理 |
| **代码质量** | Ruff | Linting + 格式化 |

### 关键特性

✅ **小核心大生态** - 核心小，通过 Markdown 扩展  
✅ **Claude Code 兼容** - `.olav/` 结构与 `.claude/` 完全对应  
✅ **多品牌支持** - Cisco/Huawei/Arista/Juniper 等  
✅ **智能路由** - LLM 自动选择合适的 skill  
✅ **生产就绪** - 完整测试、类型检查、错误处理  
✅ **易于扩展** - 添加 Markdown 即可添加新功能  

---

## 快速参考

### 常用命令

```bash
# 启动 OLAV CLI
uv run python -m olav.main

# 运行完整测试套件
uv run pytest tests/ -v

# 运行特定阶段测试
uv run pytest tests/e2e/test_phase5_comprehensive_l1l4.py -v

# 代码质量检查
uv run ruff check src/ --fix

# 类型检查
uv run mypy src/ --strict

# 生成覆盖率报告
uv run pytest --cov=src/olav --cov-report=html
```

### 文件结构

```
OLAV/
├── .olav/                     # OLAV 配置和知识库
│   ├── OLAV.md               # 核心系统提示词
│   ├── skills/               # 3个核心 skills (Markdown)
│   │   ├── device-inspection.md
│   │   ├── quick-query.md
│   │   └── deep-analysis.md
│   ├── knowledge/            # 知识库
│   │   ├── aliases.md        # 设备别名
│   │   └── topology.md       # 网络拓扑
│   ├── config/nornir/        # Nornir 库存配置
│   ├── reports/              # 生成的 HTML 报告
│   └── capabilities.db       # DuckDB 命令库
│
├── src/olav/                 # 主源代码
│   ├── agent.py             # DeepAgents 创建
│   ├── core/                # 核心模块
│   ├── tools/               # LangChain tools
│   └── main.py              # CLI 入口
│
├── tests/                    # 完整测试套件
│   ├── unit/                # 单元测试 (147+)
│   ├── e2e/                 # E2E 测试 (37+)
│   └── conftest.py          # Pytest 配置
│
├── docs/                     # 完整文档档案
├── pyproject.toml           # 项目配置 (uv)
└── README.md                # 本文件
```

---

## 文档和资源

### 核心文档

- [DESIGN_V0.8.md](docs/DESIGN_V0.8.md) - 详细设计文档
- [COMPREHENSIVE_L1L4_SIMPLIFICATION.md](docs/COMPREHENSIVE_L1L4_SIMPLIFICATION.md) - L1-L4 巡检说明
- [PHASE_5_REAL_DEVICES_GUIDE.md](docs/PHASE_5_REAL_DEVICES_GUIDE.md) - 真实设备配置指南

### 快速参考

- [COMPREHENSIVE_L1L4_QUICK_REFERENCE.md](docs/COMPREHENSIVE_L1L4_QUICK_REFERENCE.md) - 测试快速参考
- [CLI_USER_GUIDE.md](docs/CLI_USER_GUIDE.md) - CLI 使用指南
- [UV_GUIDE.md](docs/UV_GUIDE.md) - uv 包管理指南

### 阶段文档

- Phase 1: [PHASE_1_QUICKSTART.md](docs/PHASE_1_QUICKSTART.md)
- Phase 2: [PHASE_2_QUICKSTART.md](docs/PHASE_2_QUICKSTART.md)
- Phase 3: [PHASE_3_QUICKSTART.md](docs/PHASE_3_QUICKSTART.md)
- Phase 4: [PHASE_4_QUICKSTART.md](docs/PHASE_4_QUICKSTART.md)
- Phase 5: [PHASE_5_QUICKSTART.md](docs/PHASE_5_QUICKSTART.md)

---

## 获取帮助

### 遇到问题？

1. **查看日志**: `tail -f nornir.log`
2. **检查配置**: `.env` 和 `.olav/config/nornir/`
3. **运行诊断**: `uv run pytest tests/unit/ -v`
4. **查看文档**: 详见 `docs/` 目录

### 反馈和贡献

- 提交 Issue: 描述问题和重现步骤
- 提交 PR: 确保测试通过且代码符合质量标准
- 讨论功能: 在 Discussions 中提出想法

---

## 许可证

MIT License - 详见 LICENSE 文件

---

## 致谢

- **DeepAgents Framework**: 提供强大的 Agent 编排能力
- **Claude Code**: 启发了三层知识架构设计
- **Nornir**: 卓越的网络自动化框架
- **LangChain**: 灵活的 LLM 集成

---

**OLAV v0.8** - *Build Network Intelligence with AI*

**最后更新**: 2026-01-08 | **维护者**: GitHub Copilot + Claude Haiku 4.5
