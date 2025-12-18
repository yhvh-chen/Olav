# OLAV (NetAIChatOps)

<div align="center">

```
   ____  _        ___     __
  / __ \| |      / \ \   / /
 | |  | | |     / _ \ \ / / 
 | |  | | |    / ___ \ V /  
 | |__| | |___/ ___ \ | |   
  \____/|_____/_/   \_\|_|  
                            
  NetAIChatOps CLI
```

**企业级网络运维 ChatOps 平台**

[English](../README.md) | 中文版

</div>

---

## 🤖 什么是 OLAV?

OLAV 是一款专为**通过自然语言操作大规模网络**而设计的 ChatOps 工具。它允许网络工程师通过简单的对话管理数千台设备（从多厂商路由器到交换机）。

无论是“检查所有核心路由器的 BGP 状态”还是“诊断 R1 的丢包问题”，OLAV 都能将您的意图转化为精确、安全的网络命令。它使用 **LangGraph** 进行工作流编排，利用 **SuzieQ** 进行可观测性分析，并以 **NetBox** 作为单一真理源 (SSoT)。

## 🌟 核心能力

### 🧠 Agentic RAG & 架构感知
OLAV 实现了**架构感知 (Schema-Aware)** 的 RAG 模式：
- **动态工具注册**：无需为每个表硬编码工具，OLAV 使用 2 个通用工具动态查询 SuzieQ 和 OpenConfig 模型。
- **三层知识库**：情境记忆（历史成功路径）、架构索引（YANG/Avro 真理源）和文档索引。

### 🛡️ 安全与治理
- **人机协同 (HITL)**：所有写操作（NETCONF/CLI）必须经过人工审批。
- **漏斗式诊断**：自动从宏观（SuzieQ 全网分析）深入到微观（设备级 NETCONF 诊断）。
- **命令黑名单**：强制拦截 `reload`、`format` 等危险命令。

## 🚀 快速开始

### 安装
```bash
git clone https://github.com/yourusername/Olav.git
cd Olav
uv sync --dev
```

### 启动
```bash
# 初始化并运行 (Windows)
.\setup.ps1

# 启动 CLI
uv run olav
```

## 🎮 CLI 使用指南
- **交互模式**: `uv run olav`
- **专家模式 (深度诊断)**: `uv run olav -e "为什么 R1 的 BGP 在抖动？"`
- **自动化巡检**: `uv run olav inspect run daily_check`

---
授权协议：[MIT](../LICENSE)
