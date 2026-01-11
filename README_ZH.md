# 🤖 OLAV - 企业级网络运维 AI 助手

**版本**: v0.8.0
**状态**: ✅ 生产就绪 (Production Ready)
**框架**: DeepAgents Native

OLAV (Operations Language-based Autonomous Vehicle) 是一款专为生产环境设计的智能 **Agentic (代理式)** 网络助手。它弥合了 **生成式 AI** 与 **确定性网络自动化** (Nornir/Netmiko) 之间的鸿沟。

**[中文指南](README_ZH.md)** | **English Guide**

---

## 🌟 为什么选择 OLAV?

### 🧠 Agentic & Autonomous (智能代理)
基于 **DeepAgents** 框架构建，OLAV 不仅仅是一个聊天机器人。它是一个以目标为导向的 Agent，能够：
- **规划 (Plan)**: 将复杂请求（例如“审计所有 BGP 邻居”）拆解为子任务。
- **行动 (Act)**: 自主执行多步骤工作流，使用工具并检查结果。
- **反思 (Reflect)**: 在向用户汇报之前验证自己的输出。
- **记忆 (Memory)**: 在整个故障排查会话中保持上下文。

### 🔄 Claude Code 兼容
OLAV v0.8 采用了与 **Claude Code** 100% 兼容的文件结构 (`.claude/` ↔ `.olav/`)。
- **无缝迁移**: 直接将现有的 Claude Code 提示词 (prompts) 和技能 (skills) 放入 `.olav/skills`。
- **标准化 SOP**: 使用标准 Markdown 定义 Agent 遵循的健壮运维流程 (SOP)。

### 📊 Schema-Aware & Structured (结构化感知)
停止向 LLM 投喂原始文本。
- **TextFSM 原生支持**: OLAV 自动通过 TextFSM 模板运行 CLI 输出，将非结构化文本流转换为 **结构化 JSON**。
- **Token 高效**: 这种结构化感知方法减少了 50% 以上的上下文使用，并通过允许 AI 查询特定字段（如 `interface[0].status`）而不是解析文本，显着提高了分析准确性。

### 🛡️ 企业级安全
- **三层知识大脑**: 解耦 **技能 Skills** (How)、**知识 Knowledge** (What) 和 **能力 Capabilities** (Tools)。
- **人机介入 (HITL)**: 敏感命令（如 `reload`, `config`）触发强制审批门控。
- **多厂商支持**: 原生支持 Cisco, Huawei, Juniper, Arista 以及任何兼容 SSH 的设备。

---

## 🚀 快速开始

### 1. 安装
前置条件: Python 3.10+

```bash
# 使用 uv 安装 (推荐，速度更快)
pip install uv
uv sync
```

### 2. 配置 (环境)
从模板创建配置文件：

```bash
cp .env.example .env
# 编辑 .env 添加你的 LLM API Key (OpenAI, DeepSeek 等)
```

### 3. 网络清单设置 (关键步骤)
OLAV 使用 Nornir 与网络交互。你必须在 `.olav/config/nornir/hosts.yaml` 中定义设备。
*注意：这是 OLAV 知道设备存在的唯一途径。*

1. 复制示例文件：
   ```bash
   cp .olav/config/nornir/hosts.yaml.example .olav/config/nornir/hosts.yaml
   ```
2. 编辑 `hosts.yaml` 填入你的实际设备信息。**此文件已被 git-ignored** 以保护凭据。

```yaml
# 示例 .olav/config/nornir/hosts.yaml
R1:  # <-- 聊天中使用的别名 (例如 "检查 R1")
  hostname: 192.168.10.1
  platform: cisco_ios
  username: admin
  password: password123 
  groups: ["core", "routers"]
```

### 4. 初始化 (一次性)
你 **必须** 运行此脚本来索引设备、加载命令白名单并构建向量数据库。

```bash
uv run python scripts/init_capabilities.py
```
*输出示例: "Successfully loaded X commands, Y devices..."*

### 5. 启动
启动交互式 Agent CLI：

```bash
uv run olav.py
```

---

## 💻 工作流与 CLI

OLAV 在两种模式下运行：**自然语言** (Agentic) 和 **工作流** (确定性)。

### Agentic Chat (自然语言对话)
描述你想要做什么，Agent 会使用其技能规划执行步骤。
> "检查核心路由器上 OSPF 翻滚的原因"
> "审计 Access-01 和 Dist-01 之间的 VLAN 一致性"

### Workflow Commands (`/`) (工作流命令)
对于频繁的任务，使用 Slash 命令触发 **Schema-Aware 工作流**。这些比自由格式聊天更快、更便宜（Token 更少）且更可靠。

**详细用法:**

*   **`/analyze [query]`**: 启动 MicroAnalyzer 子 Agent。
    *   *示例*: `/analyze "Why is BGP peering down on Core-01?"` (为什么Core-01的BGP对等体断开了？)
*   **`/inspect [target]`**: 运行健康巡检 (L1-L4)。
    *   *示例*: `/inspect group:core` 或 `/inspect R1`
*   **`/backup`**: 备份所有或特定设备的 running-config。
    *   *示例*: `/backup` (所有) 或 `/backup group:access`

| 命令 | 描述 | Agentic 级别 |
|---------|-------------|---------------|
| `/analyze` | **深度诊断**: 启动 MicroAnalyzer 子代理进行根因分析。 | ⭐⭐⭐ |
| `/inspect` | **健康巡检**: 基于已知 Schema 运行 L1-L4 检查。 | ⭐⭐ |
| `/backup` | **配置备份**: 保存 running-config 的标准化工作流。 | ⭐ |
| `/search` | **RAG 搜索**: 本地知识库 (.md) 和 Web 的混合搜索。 | ⭐ |
| `/devices` | **清单**: 列出连接的设备及其连接状态。 | - |
| `/skills` | **技能清单**: 列出已加载的 Markdown SOP。 | - |
| `/stats` | **Token 统计**: 显示成本和 Token 消耗统计。 | - |
| `/plan` | **调试**: 显示 Agent 当前的思维链和计划。 | - |
| `/clear` | 清屏。 | - |
| `/quit` | 退出。 | - |

---

## 🛠️ 高级特性

### 1. Schema-Aware 解析 (TextFSM)
教 OLAV 如何解析新命令：
1.  将 NTC-template 文件放入 `.olav/config/textfsm/`。
2.  在 `.olav/config/textfsm/index` 中更新索引文件。

OLAV 将优先向 LLM 发送 `JSON` 对象而不是原始文本块，从而实现“结构化感知”推理。

### 2. 添加技能 (Claude Code 兼容)
在 `.olav/skills/` 中创建一个 Markdown 文件，以传授新的标准操作程序 (SOP)。OLAV 原生读取 **Claude Code** 技能格式。

**迁移助手**:
想转换现有的 Skills 到新格式？使用内置工具：
```bash
uv run python scripts/migrate_to_claude_code.py --path ./old_skills/
```

**示例: `.olav/skills/daily-check.md`**
```markdown
---
name: daily-check
description: 对边缘路由器执行每日健康检查
version: 1.0
---
# Procedure
1. Execute `/inspect` workflow on group "edge".
2. Check for "High CPU" log patterns.
3. Report anomalies.
```

### 3. 添加工作流 (Workflows)
要将 Skill 暴露为 Slash 命令 (工作流):
1. 如上所述创建 skill markdown 文件。
2. 在 `.olav/config/commands.yaml` 中注册 (或者依赖自动加载器的搜索功能)。
*注意: `/analyze` 等高优先级工作流是为了性能而硬编码的。*

### 4. 知识库 (RAG) 与 标准路径
OLAV 遵循 **"文档即真理" (Documents as Truth)** 哲学。

**默认文件位置:**
| 功能 | 输入/输出 | 路径 | 格式 |
|---|---|---|---|
| **知识库 (KB)** | 输入 | `.olav/knowledge/` | `.md`, `.txt`, `.pdf` |
| **报告 (Reports)** | 输出 | `.olav/reports/` | `.html` (仪表板), `.json` |
| **技能 (Skills)** | 输入 | `.olav/skills/` | `.md` (Claude Code 格式) |
| **资产清单 (Inventory)** | 输入 | `.olav/config/nornir/hosts.yaml` | YAML |

**使用方法:**
- 将本地站点文档放入 `knowledge/` 并运行 `uv run python scripts/index_knowledge.py`。
- 在 `reports/` 目录下查找生成的健康检查报告（来自 `/inspect` 或 `/analyze`）。
OLAV 遵循 **"文档即真理" (Documents as Truth)** 哲学。
- 将你的站点文档 (PDF/MD) 放入 `.olav/knowledge/`。
- 运行 `uv run python scripts/index_knowledge.py` 进行向量化。
- 使用 `/search` 在故障排查期间检索此特定上下文。

---

## 🏗️ 架构

- **运行时**: Python 3.12 + `uv`
- **Agent 框架**: DeepAgents
- **数据库**: DuckDB (Vector + Relational)
- **执行层**: Nornir (并发) + Netmiko (SSH)
- **协议**: SSH, Telnet, NETCONF

## 📄 许可证与支持

**MIT License** - Open Source & Enterprise Ready.
详细架构文档见 `docs/` 文件夹。
