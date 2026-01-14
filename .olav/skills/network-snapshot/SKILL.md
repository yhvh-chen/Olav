---
name: Network Snapshot
description: Network data collection definitions (formerly daily-sync)
version: 2.0.0
intent: snapshot
# schedule 由 daily-run workflow 控制，此处不单独定义
---

## Network Snapshot - 采集定义

通过 `search_capabilities(intent, platform)` 动态查询命令。

### 执行参数

#### 群组选择 (MANDATORY)
- `group="test"` (默认) - 测试设备 (192.168.100.x)
- `group="core"` - 生产核心设备
- `group="border"` - 边界设备

#### 设备过滤 (可选)
- `devices="all"` (默认) - 所有设备
- `devices="R1,R2,R3"` - 指定设备名称

### 两阶段流程设计

**Stage 1 (快速数据收集)**:
- 使用Nornir并行执行命令（快速）
- 命令结果落盘到 `data/sync/YYYY-MM-DD/raw/`
- 立即返回，不阻塞用户

**Stage 2 (异步后处理)**:
- 后台线程运行解析、数据库初始化、LLM分析
- 生成报告到 `data/sync/YYYY-MM-DD/reports/`
- 不影响Stage 1的响应时间

### 采集类别

#### configs
- intent: "running configuration"
- intent: "startup configuration"

#### neighbors
- intent: "cdp neighbors"
- intent: "lldp neighbors"

#### routing
- intent: "ospf neighbors"
- intent: "bgp summary"
- intent: "routing table"

#### interfaces
- intent: "interface status"
- intent: "interface counters"

#### system
- intent: "device version"
- intent: "cpu usage"
- intent: "memory usage"

#### environment
- intent: "environment status"
- intent: "power status"

#### logging
- intent: "device logging"
- parse: true  # 需要事件解析

## 使用方式

此 Skill 由 `/sync` 命令或 `/daily-run` workflow 的 Stage 1 调用。

工具函数: `sync_all(devices="all", categories=None)`

## 输出

采集数据存储在 `data/sync/YYYY-MM-DD/`:
- `configs/`: 配置文件
- `raw/<category>/`: 原始命令输出
- `parsed/<category>/`: TextFSM 解析结果 (可选)
