# 🤖 OLAV - 网络运维智能助手

**版本**: 0.8.0  
**状态**: ✅ Phase 1-5 完全可用  
**架构**: DeepAgents Native + 三层知识架构 (Skills/Knowledge/Tools)  
**平台**: 兼容 Claude Code, 支持 Windows/Mac/Linux

**[中文指南](zh.md)** | **[English Guide](../README.md)**

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
uv run python -m olav.main "巡检所有 lab 设备"

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

#### 2. **Quick Query** - 快速查询
- 1-2 个命令快速响应
- 自动命令选择
- 面向多品牌网络设备 (Cisco/Huawei/Arista)

```bash
"检查 R1 CPU 使用率"
"显示 S1 接口状态"
"获取 R2 的 BGP 邻居"
```

#### 3. **Deep Analysis** - 深度分析
- 多步骤复杂诊断
- 自动问题定位
- 提供修复建议

```bash
"诊断 R1 的 BGP 邻居为何掉线"
"分析核心交换机上的接口错误率"
"检查网络安全基线合规性"
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
uv run python -m olav.main "检查设备连接"
```

---

## 使用示例

### 示例 1: 基础设备查询

```bash
# 方式 A: CLI
$ uv run python -m olav.main "R1 接口状态"

# 预期结果:
# R1 Gi0/1: UP, 1000Mbps
# R1 Gi0/2: UP, 1000Mbps
# R1 Gi0/3: DOWN
```

### 示例 2: 全面设备巡检

```bash
# 对所有 lab 设备执行 L1-L4 全面巡检
$ uv run python -m olav.main "巡检所有 lab 设备并执行全面 L1-L4 健康检查"

# 生成的报告:
# .olav/reports/lab-comprehensive-l1l4-20260108-143000.html
#   ├─ Executive Summary (所有8个设备的整体状态)
#   ├─ L1-L4 分层数据
#   ├─ 异常检测和标记
#   └─ 修复建议
```

### 示例 3: 深度分析工作流

```bash
# 复杂的多步诊断
$ uv run python -m olav.main "诊断 R1 上的 BGP 闪振问题并提供修复步骤"

# 预期工作流:
# 1. 检查 BGP 邻接体状态
# 2. 分析接口稳定性
# 3. 审查路由表
# 4. 检查路由器 CPU/内存
# 5. 提供建议
```

### 示例 4: 在 Claude Code 中使用

```
Claude Code 提示词:

"使用 OLAV skills 执行以下任务:
1. 巡检所有 lab 设备
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

## 文件结构

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
├── i18n/                     # 国际化
│   └── zh.md                # 中文指南
│
├── pyproject.toml           # 项目配置 (uv)
└── README.md                # 英文指南
```

---

## 快速参考

### 常用命令

```bash
# 启动 OLAV CLI
uv run python -m olav.main

# 执行设备巡检
uv run python -m olav.main "巡检所有 lab 设备"

# 查询单一设备
uv run python -m olav.main "检查 R1 状态"

# 代码质量检查
uv run ruff check src/ --fix

# 类型检查
uv run mypy src/ --strict
```

---

## 获取帮助

### 遇到问题？

1. **查看日志**: `tail -f nornir.log`
2. **检查配置**: `.env` 和 `.olav/config/nornir/`
3. **运行诊断**: `uv run python -m olav.main "测试连接"`

### 反馈和贡献

- **提交 Issue**: 描述问题和重现步骤
- **提交 PR**: 确保代码质量
- **讨论功能**: 分享你的想法

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
