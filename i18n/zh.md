# 🤖 OLAV - 企业网络运维 AI 助手

**版本**: 0.8.0  
**状态**: ✅ 生产就绪  
**架构**: DeepAgents Native + 三层知识架构 (Skills/Knowledge/Tools)  
**CLI**: 交互式 DeepAgent CLI  
**平台**: 兼容 Claude Code，支持 Windows/Mac/Linux

**[中文指南](zh.md)** | **[English Guide](../README.md)**

---

## 📋 目录

- [快速开始](#快速开始)
- [功能概览](#功能概览)
- [安装](#安装)
- [使用示例](#使用示例)
- [备份指南](#备份使用指南)
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

### 2️⃣ 启动交互式 CLI

```bash
# 启动 DeepAgent CLI
uv run python -m olav.main

# 欢迎使用 OLAV 交互式 CLI
# 输入 /help 查看可用命令
```

### 3️⃣ 在 CLI 中使用斜杠命令

```
OLAV> /devices
✅ R1, R2, R3, R4, SW1, SW2 (连接中)

OLAV> 检查 R1 接口状态
🔍 匹配到 'quick-query' Skill
...

OLAV> /inspect layer3
📊 L3 巡检报告
...

OLAV> /skills
📚 可用 Skills: device-inspection, quick-query, deep-analysis, config-backup

OLAV> /history
📜 最近命令...

OLAV> /quit
```

### 4️⃣ 在 Claude Code 中使用

```
1. 进入项目目录
2. 在 Claude Code 中打开
3. OLAV CLI 自动与代理集成
4. 查看可用 Skill: `/skills`
5. 发送命令: "备份所有核心角色设备的运行配置"
```

---

## 功能概览

### 🎯 四大核心能力

#### 1. **Device Inspection** - 全面设备巡检
- **L1 物理层**: CPU/内存/温度/电源/风扇
- **L2 数据链路**: VLAN/STP/LLDP/MAC表
- **L3 网络层**: 路由/OSPF/BGP/VPNv4
- **L4 传输层**: TCP/进程/内存/错误计数

#### 2. **Quick Query** - 快速查询
- 1-2 个命令快速响应
- 自动命令选择
- 面向多品牌网络设备 (Cisco/Huawei/Arista)

示例:
```
"检查 R1 CPU 使用率"
"显示 SW1 接口状态"
"获取 R3 的 BGP 邻居"
```

#### 3. **Deep Analysis** - 深度分析
- 多步骤复杂诊断
- 自动问题定位
- 提供修复建议

示例:
```
"诊断 R1 的 BGP 邻居为何掉线"
"分析核心交换机上的接口错误率"
"检查网络安全基线合规性"
```

#### 4. **Device Backup** - 智能配置备份
- 按 group/role/site 灵活过滤
- 单台或批量设备备份
- 自动文件命名和时间戳
- Git 版本控制集成

示例:
```
"备份所有核心角色设备的运行配置"
"保存 test 组的启动配置"
"备份 border 角色设备的 running-config"
```

---

## 安装

### 前置要求

- **Python 3.11+** (推荐 3.13)
- **uv** 包管理器 (快速安装: `pip install uv`)
- **网络设备** (Cisco IOS/XE, Huawei, Arista 等)
- **SSH 访问权限** 到网络设备

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

# 4. 配置 Nornir (网络设备清单)
# 编辑 .olav/config/nornir/hosts.yaml
# 编辑 .olav/config/nornir/groups.yaml

# 5. 启动交互式 CLI 并测试
uv run python -m olav.main

# 在 CLI 中测试基本命令:
# OLAV> /devices
# OLAV> 检查设备连接性
# OLAV> /quit
```

---

## 使用示例

### 示例 1: 启动 CLI 并查询设备

```bash
# 启动交互式 CLI
$ uv run python -m olav.main

# OLAV> R1 接口状态
# 🔍 匹配到 'quick-query' Skill
# 执行: show ip interface brief on R1
# ...
# ✅ 任务完成
#
# OLAV>
```

### 示例 2: 查看可用设备

```bash
# OLAV> /devices
# 📋 连接的设备:
#   R1 (Cisco IOS) - Group: test, Role: border, Site: lab
#   R2 (Cisco IOS) - Group: test, Role: border, Site: lab
#   R3 (Cisco IOS) - Group: test, Role: core, Site: lab
#   R4 (Cisco IOS) - Group: test, Role: core, Site: lab
#   SW1 (Cisco IOS) - Group: test, Role: access, Site: lab
#   SW2 (Cisco IOS) - Group: test, Role: access, Site: lab
```

### 示例 3: 执行全面巡检

```bash
# OLAV> 巡检所有 lab 设备，进行完整的 L1-L4 检查
# 🔍 匹配到 'device-inspection' Skill
# 📊 lab 组 L1-L4 巡检报告
#   ├─ 执行摘要 (6 个设备的总体状态)
#   ├─ L1 物理层: CPU/内存/温度/电源 ✅
#   ├─ L2 数据链路: VLAN/STP/LLDP ✅
#   ├─ L3 网络层: 路由/OSPF/BGP ✅
#   ├─ L4 传输层: TCP/进程 ✅
#   └─ 异常检测: 未发现异常
#
# 📁 报告已保存: .olav/reports/lab-comprehensive-l1l4-20260108-143000.html
```

### 示例 4: 使用文件引用和 Shell 命令

```bash
# OLAV> 分析这个配置文件 @network-config.txt 是否符合最佳实践
# 📄 文件已加载: network-config.txt (1024 字节)
# 🔍 匹配到 'deep-analysis' Skill
# ...

# OLAV> !ping -c 4 192.168.1.1 && 检查 R1 是否响应
# $ ping -c 4 192.168.1.1
# PING 192.168.1.1 (192.168.1.1) 56(84) bytes of data
# ...
# ✅ R1 响应正常，丢包率 0%
```

### 示例 5: 备份设备配置

```bash
# 单台设备备份
OLAV> 备份 R1 运行配置
🔍 匹配到 'config-backup' Skill
📁 正在保存 R1 运行配置
✅ 已保存至: .olav/data/configs/R1-running-config-20260108-120000.txt

# 按角色备份
OLAV> 备份所有核心角色设备的运行配置
🔍 匹配到 'config-backup' Skill
📁 找到 2 个核心设备: R3, R4
✅ 正在保存 R3 运行配置
✅ 正在保存 R4 运行配置

# 按组备份
OLAV> 备份 test 组的启动配置
🔍 匹配到 'config-backup' Skill
📁 找到 6 个 test 组设备
✅ 保存完成 (6 个文件)

# 按站点备份
OLAV> 备份所有 lab 站点设备的运行配置
🔍 匹配到 'config-backup' Skill
📁 找到 6 个 lab 站点设备
✅ 批量备份完成 (6 个文件已保存)
```

---

## 备份使用指南

### 设备过滤选项

备份 Skill 支持多种过滤方式:

| 过滤类型 | 语法 | 示例 |
|---------|------|------|
| **单台设备** | 设备名称 | `备份 R1 运行配置` |
| **多台设备** | 逗号分隔 | `备份 R1,R2,R3 运行配置` |
| **按角色** | `role:` 前缀 | `备份 role:core 运行配置` |
| **按组** | `group:` 前缀 | `备份 group:test 运行配置` |
| **按站点** | `site:` 前缀 | `备份 site:lab 运行配置` |
| **所有设备** | `all` 关键字 | `备份所有设备运行配置` |

### 备份文件位置

所有备份自动保存到 `.olav/data/configs/`，并使用时间戳命名:

```
.olav/data/configs/
├── R1-running-config-20260108-120000.txt
├── R2-running-config-20260108-120000.txt
├── R3-startup-config-20260108-120000.txt
└── ...
```

### 查看可用设备

```bash
OLAV> /devices
📋 可用设备 (含属性):

设备 | 组 | 角色 | 站点
-----|------|------|------
R1   | test   | border | lab
R2   | test   | border | lab
R3   | test   | core | lab
R4   | test   | core | lab
SW1  | test   | access | lab
SW2  | test   | access | lab
```

### 使用 Git 进行版本控制

使用 Git 追踪配置变化:

```bash
# 初始化 (仅一次)
cd .olav/data
git init
git config user.name "OLAV Backup"

# 备份后
git add configs/
git commit -m "Backup $(date +%Y%m%d-%H%M%S)"

# 查看备份历史
git log --oneline | head -10
```

---

## 高级用法

### 三层知识架构

```
┌────────────────────────────────────────────────────────┐
│          OLAV 三层知识架构                              │
├────────────────────────────────────────────────────────┤
│                                                        │
│  第 1 层: SKILLS (.olav/skills/*.md)                   │
│  ├─ device-inspection    → 全面 L1-L4 巡检            │
│  ├─ quick-query          → 快速 1-2 个命令查询         │
│  ├─ deep-analysis        → 多步骤诊断                   │
│  └─ config-backup        → 配置备份                     │
│     [策略层 - HOW: 如何执行任务]                       │
│                                                        │
│  第 2 层: KNOWLEDGE (.olav/knowledge/*.md)             │
│  ├─ aliases.md           → 设备别名映射                │
│  └─ topology.md          → 网络拓扑                     │
│     [知识层 - WHAT: 是什么]                            │
│                                                        │
│  第 3 层: TOOLS/CAPABILITIES                           │
│  ├─ Nornir               → SSH 批量执行                │
│  ├─ smart_query          → 统一查询工具                │
│  ├─ DuckDB              → CLI/API/NETCONF 库           │
│  └─ LangChain           → LLM 集成                     │
│     [能力层 - CAN: 我们能做什么]                       │
│                                                        │
└────────────────────────────────────────────────────────┘
```

### 执行流程

```
用户输入
  ↓
┌─────────────────────────┐
│ LLM Skill 路由器         │
│ (意图识别 + 路由)        │
└──────────┬──────────────┘
           ↓
      选择 Skill
           ↓
┌──────────────────────────┐
│ Skill 执行引擎           │
│ (解析范围 + 执行命令)    │
└──────────┬───────────────┘
           ↓
    Nornir 批量执行
           ↓
┌──────────────────────────┐
│ 报告生成                  │
│ (Jinja2 模板 + HTML)     │
└──────────┬───────────────┘
```

---

## 架构设计

### 核心技术栈

| 组件 | 技术 | 用途 |
|-----|------|------|
| **框架** | DeepAgents | 代理编排和 HITL |
| **LLM** | OpenAI/Claude | 意图识别和路由 |
| **CLI** | prompt-toolkit 3.0+ | 交互式命令界面 |
| **网络** | Nornir 3.3 | 多设备批量执行 |
| **数据库** | DuckDB 0.8 | 轻量级能力库 |
| **模板** | Jinja2 3.1 | HTML 报告生成 |
| **包管理** | uv | 快速依赖管理 |

### 关键特性

✅ **小核心，大生态** - 小核心通过 Markdown 扩展  
✅ **Claude Code 兼容** - `.olav/` 结构与 `.claude/` 对齐  
✅ **多品牌支持** - Cisco/Huawei/Arista/Juniper 等  
✅ **智能路由** - LLM 自动选择合适的 Skill  
✅ **生产就绪** - 完整错误处理、类型提示、验证  
✅ **易于扩展** - 通过添加 Markdown 文件添加新功能  

---

## 文件结构

```
OLAV/
├── .olav/                     # OLAV 配置和知识库
│   ├── OLAV.md               # 核心系统提示
│   ├── skills/               # 核心 Skills (Markdown)
│   │   ├── device-inspection.md      # L1-L4 巡检
│   │   ├── quick-query.md            # 快速查询
│   │   ├── deep-analysis.md          # 复杂诊断
│   │   └── config-backup.md          # 配置备份
│   ├── knowledge/            # 知识库
│   │   ├── aliases.md        # 设备别名映射
│   │   └── topology.md       # 网络拓扑
│   ├── config/nornir/        # Nornir 清单配置
│   ├── data/
│   │   └── configs/          # 备份存储目录
│   ├── reports/              # 生成的 HTML 报告
│   └── capabilities.db       # DuckDB 命令库
│
├── src/olav/                 # 主源代码
│   ├── agent.py             # DeepAgents 代理创建
│   ├── main.py              # CLI 入口
│   ├── core/                # 核心模块
│   └── tools/               # LangChain 工具
│
├── i18n/                     # 国际化
│   └── zh.md                # 中文指南
│
├── tests/                    # 测试套件
├── pyproject.toml           # 项目配置 (uv)
└── README.md                # 说明文件
```

---

## 快速参考

### 常见命令

```bash
# 🚀 启动交互式 CLI
uv run python -m olav.main

# 📋 在 CLI 中 - 查看可用设备
/devices
/devices [group]

# 📚 在 CLI 中 - 显示可用 Skills
/skills
/skills [skill_name]

# 🔍 在 CLI 中 - 快速巡检
/inspect [layer|scope]

# 📁 在 CLI 中 - 列出备份
/backups

# 📜 在 CLI 中 - 显示命令历史
/history

# 🧹 在 CLI 中 - 清除内存
/clear

# ❓ 在 CLI 中 - 帮助
/help

# 🚪 在 CLI 中 - 退出
/quit
```

---

## 支持

### 故障排查

1. **找不到设备**: 检查 `.olav/config/nornir/hosts.yaml` 和 `.env` 中的凭证
2. **命令超时**: 增加 Nornir 配置中的 SSH 超时时间
3. **备份文件保存失败**: 验证 `.olav/data/configs/` 目录存在且可写

### 常见问题

**Q: 如何添加新设备?**
A: 编辑 `.olav/config/nornir/hosts.yaml`，使用 group 和 role 信息添加设备条目。

**Q: 我可以备份特定配置部分吗?**
A: 在 Skill 中使用自然语言: "备份核心设备的接口配置" - Skill 会自动确定最佳方法。

**Q: 备份文件如何组织?**
A: 所有备份都保存到 `.olav/data/configs/`，格式为 `[设备]-[配置类型]-[时间戳].txt`

---

## 许可证

MIT License - 详见 LICENSE 文件

---

**OLAV v0.8** - *用 AI 构建网络智能*  
**最后更新**: 2026-01-08 | **维护者**: GitHub Copilot + Claude Haiku 4.5
