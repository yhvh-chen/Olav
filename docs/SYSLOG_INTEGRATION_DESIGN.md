# Syslog 集成设计方案

**状态**: 待实施  
**优先级**: P2 (增强功能)  
**预计工作量**: 2-3 天

## 1. 背景与动机

### 1.1 当前架构数据源

```
┌─────────────────────────────────────────────────────────────┐
│  结构化数据 (Schema-Aware)                                   │
│  ├── SuzieQ (Parquet) → 宏观历史分析 (只读)                  │
│  ├── NETCONF/gNMI → 微观实时诊断 (读写+HITL)                 │
│  └── NetBox API → 设备资产 (SSOT)                           │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 缺失的能力

**事件驱动诊断**: 设备原始日志（Syslog）是故障发生的**第一手信号源**，当前架构无法获取。

**典型场景**:
```
用户: "昨晚 R1 的 BGP 为什么 flap？"

当前流程:
  1. SuzieQ 查询 BGP 历史 → 发现 flap 时间点
  2. NETCONF 查询当前状态 → 已恢复
  3. ❌ 无法知道 flap 的触发原因

增强后流程:
  1. SuzieQ 查询 BGP 历史 → 发现 flap 时间点 (02:30-02:45)
  2. 搜索 Syslog → 找到 "LINK-DOWN Gi0/1" 事件 (02:29)
  3. ✅ 根因: 物理链路故障导致 BGP 邻居断开
```

---

## 2. 方案选型

### 2.1 方案对比

| 维度 | 方案 A: 直读 Syslog | 方案 B: Syslog → OpenSearch |
|------|---------------------|----------------------------|
| **组件数量** | 1 个 (rsyslog) | 2 个 (rsyslog + OpenSearch) |
| **复杂度** | ⭐⭐ 低 | ⭐⭐⭐ 中 |
| **查询能力** | grep/awk (正则) | 全文搜索 + 聚合 |
| **时间范围查询** | 慢（扫描文件） | 快（索引优化） |
| **多设备关联** | 困难 | 简单（device_ip 字段） |
| **存储管理** | logrotate | OpenSearch ILM |
| **与现有架构** | 新增独立组件 | 复用现有 OpenSearch |
| **工具实现** | 执行 shell 命令 | HTTP API 调用 |

### 2.2 查询性能对比

**方案 A (grep)**:
```bash
# 查询 R1 过去1小时的 BGP 相关日志
grep "BGP" /var/log/network/R1.log | grep -E "$(date -d '1 hour ago' +'%Y-%m-%d %H')"
```
- ❌ 大文件时慢（顺序扫描）
- ❌ 多条件组合复杂
- ❌ 时间范围查询需要解析每行

**方案 B (OpenSearch)**:
```json
{
  "query": {
    "bool": {
      "must": [
        { "match": { "raw_message": "BGP" } },
        { "term": { "device_ip": "10.0.0.1" } }
      ],
      "filter": {
        "range": { "@timestamp": { "gte": "now-1h" } }
      }
    }
  }
}
```
- ✅ 毫秒级响应（倒排索引）
- ✅ 天然支持时间范围
- ✅ 可与其他 OpenSearch 索引关联

### 2.3 决策

**选择方案 B: Syslog → OpenSearch**

**理由**:
1. **复用现有基础设施**: OpenSearch 已存在，无需新增组件类型
2. **统一查询接口**: 所有工具都用 OpenSearch API，架构一致
3. **性能优势**: 时间范围 + 关键词查询是常见操作，索引比 grep 快 100x
4. **扩展性**: 未来可加结构化解析或向量化，不需重构
5. **存储管理**: OpenSearch ILM 比 logrotate 更灵活

---

## 3. 架构设计

### 3.1 数据流

```
┌──────────────┐     UDP 514      ┌──────────────┐      ┌─────────────┐
│ 网络设备     │ ───────────────▶ │ rsyslog      │ ───▶ │ OpenSearch  │
│ (Cisco/Juniper/Huawei)          │ container    │      │ (syslog-raw)│
└──────────────┘                  └──────────────┘      └──────┬──────┘
                                   (omelasticsearch)           │
                                                               ▼
                                                       ┌──────────────────┐
                                                       │ syslog_search    │
                                                       │ tool (Agent)     │
                                                       └──────────────────┘
```

### 3.2 增强后的漏斗式排错

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: 宏观历史 (SuzieQ)                                  │
│  - 识别异常时间窗口                                          │
│  - 确定受影响的设备/协议                                     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: 事件日志 (Syslog) ← 新增                           │
│  - 搜索异常时间窗口的相关日志                                │
│  - 定位触发事件 (LINK-DOWN, CONFIG_CHANGE, etc.)            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: 微观实时 (NETCONF/gNMI)                            │
│  - 验证当前状态                                              │
│  - 执行修复操作 (HITL)                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 实现细节

### 4.1 Docker Compose 配置

```yaml
# docker-compose.yml 新增
services:
  rsyslog:
    image: rsyslog/syslog_appliance_alpine:latest
    container_name: olav-rsyslog
    ports:
      - "514:514/udp"
      - "514:514/tcp"
    volumes:
      - ./config/rsyslog/rsyslog.conf:/etc/rsyslog.conf:ro
    depends_on:
      opensearch:
        condition: service_started
    networks:
      - olav-network
    restart: unless-stopped
```

### 4.2 rsyslog 配置

```conf
# config/rsyslog/rsyslog.conf

# 加载必要模块
module(load="imudp")
module(load="imtcp")
module(load="omelasticsearch")

# 监听 UDP/TCP 514
input(type="imudp" port="514")
input(type="imtcp" port="514")

# JSON 模板（最简，不解析）
template(name="syslog-json" type="list") {
    constant(value="{")
    constant(value="\"@timestamp\":\"")
    property(name="timereported" dateFormat="rfc3339")
    constant(value="\",\"device_ip\":\"")
    property(name="fromhost-ip")
    constant(value="\",\"facility\":\"")
    property(name="syslogfacility-text")
    constant(value="\",\"severity\":\"")
    property(name="syslogseverity-text")
    constant(value="\",\"raw_message\":")
    property(name="rawmsg" format="jsonf")
    constant(value="}")
}

# 输出到 OpenSearch
action(
    type="omelasticsearch"
    server="opensearch"
    serverport="9200"
    searchIndex="syslog-raw"
    template="syslog-json"
    bulkmode="on"
    queue.type="linkedlist"
    queue.size="10000"
    queue.dequeuebatchsize="500"
    action.resumeretrycount="-1"
)

# 同时保留本地文件（可选，用于调试）
# action(type="omfile" file="/var/log/network.log")
```

### 4.3 OpenSearch 索引配置

```python
# src/olav/etl/init_syslog_index.py
"""Initialize syslog-raw index for device log collection."""

import logging
from opensearchpy import OpenSearch
from olav.core.settings import settings

logger = logging.getLogger(__name__)

INDEX_NAME = "syslog-raw"

INDEX_SETTINGS = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "index.lifecycle.name": "syslog-policy",  # ILM 策略
        "index.lifecycle.rollover_alias": "syslog"
    },
    "mappings": {
        "properties": {
            "@timestamp": {"type": "date"},
            "device_ip": {"type": "ip"},
            "facility": {"type": "keyword"},
            "severity": {"type": "keyword"},
            "raw_message": {
                "type": "text",
                "analyzer": "standard"
            }
        }
    }
}

# ILM 策略：7 天保留
ILM_POLICY = {
    "policy": {
        "phases": {
            "hot": {
                "actions": {
                    "rollover": {
                        "max_size": "5gb",
                        "max_age": "1d"
                    }
                }
            },
            "delete": {
                "min_age": "7d",
                "actions": {
                    "delete": {}
                }
            }
        }
    }
}


def main() -> None:
    """Create syslog-raw index with ILM policy."""
    logger.info("Initializing syslog-raw index...")
    
    client = OpenSearch(
        hosts=[settings.opensearch_url],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
    )
    
    # 创建 ILM 策略
    try:
        client.transport.perform_request(
            "PUT",
            "/_plugins/_ism/policies/syslog-policy",
            body=ILM_POLICY
        )
        logger.info("✓ Created ILM policy: syslog-policy")
    except Exception as e:
        logger.warning(f"ILM policy may already exist: {e}")
    
    # 创建索引
    if not client.indices.exists(index=INDEX_NAME):
        client.indices.create(index=INDEX_NAME, body=INDEX_SETTINGS)
        logger.info(f"✓ Created index: {INDEX_NAME}")
    else:
        logger.info(f"Index {INDEX_NAME} already exists")
    
    logger.info("✓ Syslog index initialization complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
```

### 4.4 Syslog 搜索工具

```python
# src/olav/tools/syslog_tool.py
"""Syslog search tool for event-driven diagnostics."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from olav.core.memory import OpenSearchMemory
from olav.tools.base import BaseTool, ToolOutput, ToolRegistry

logger = logging.getLogger(__name__)


class SyslogSearchTool(BaseTool):
    """Search device syslog for event-driven diagnostics.
    
    Use this tool to:
    - Find fault trigger events (LINK-DOWN, BGP-NEIGHBOR-LOST)
    - Correlate with SuzieQ time windows
    - Verify configuration change effects
    """

    def __init__(self, memory: OpenSearchMemory | None = None) -> None:
        self._name = "syslog_search"
        self._description = (
            "Search device Syslog logs for event-driven diagnostics. "
            "Use after suzieq_query identifies an anomaly time window. "
            "Searches raw log messages by keyword, device IP, and time range."
        )
        self._memory = memory

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def memory(self) -> OpenSearchMemory:
        if self._memory is None:
            self._memory = OpenSearchMemory()
        return self._memory

    async def execute(
        self,
        keyword: str,
        device_ip: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        severity: str | None = None,
        limit: int = 50,
    ) -> ToolOutput:
        """Search syslog for matching events.
        
        Args:
            keyword: Text to search in log messages (e.g., "BGP", "LINK-DOWN", "CONFIG")
            device_ip: Filter by device IP address (optional)
            start_time: Start of time range (ISO 8601 or "now-1h")
            end_time: End of time range (ISO 8601 or "now")
            severity: Filter by severity (e.g., "error", "warning", "notice")
            limit: Maximum results to return (default: 50)
        
        Returns:
            ToolOutput with matching log entries
        """
        try:
            # Build query
            must_clauses = [{"match": {"raw_message": keyword}}]
            filter_clauses = []
            
            if device_ip:
                filter_clauses.append({"term": {"device_ip": device_ip}})
            
            if severity:
                filter_clauses.append({"term": {"severity": severity.lower()}})
            
            if start_time or end_time:
                time_range = {}
                if start_time:
                    time_range["gte"] = start_time
                if end_time:
                    time_range["lte"] = end_time
                filter_clauses.append({"range": {"@timestamp": time_range}})
            
            query = {"bool": {"must": must_clauses}}
            if filter_clauses:
                query["bool"]["filter"] = filter_clauses
            
            # Execute search
            results = await self.memory.search_schema(
                index="syslog-raw",
                query=query,
                size=limit,
            )
            
            # Format results
            formatted = [
                {
                    "timestamp": r.get("@timestamp"),
                    "device_ip": r.get("device_ip"),
                    "severity": r.get("severity"),
                    "message": r.get("raw_message"),
                }
                for r in results
            ]
            
            return ToolOutput(
                source=self.name,
                device=device_ip or "all",
                data=formatted,
                metadata={
                    "keyword": keyword,
                    "result_count": len(formatted),
                    "time_range": {"start": start_time, "end": end_time},
                },
                error=None,
            )
            
        except Exception as e:
            logger.exception("Syslog search failed")
            return ToolOutput(
                source=self.name,
                device=device_ip or "unknown",
                data=[],
                metadata={},
                error=f"Syslog search error: {e}",
            )


# Register tool
ToolRegistry.register(SyslogSearchTool())


# Compatibility wrapper
@tool
async def syslog_search(
    keyword: str,
    device_ip: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    severity: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Search device Syslog logs for event-driven diagnostics.
    
    Use after suzieq_query to find the trigger event for an anomaly.
    
    Args:
        keyword: Text to search (e.g., "BGP", "LINK-DOWN", "CONFIG_CHANGE")
        device_ip: Filter by device IP
        start_time: Start time (ISO 8601 or "now-1h")
        end_time: End time (ISO 8601 or "now")
        severity: Filter by severity (error, warning, notice, info)
        limit: Max results (default: 50)
    
    Examples:
        # Find BGP events in last hour
        syslog_search(keyword="BGP", start_time="now-1h")
        
        # Find errors on specific device
        syslog_search(keyword="DOWN", device_ip="10.0.0.1", severity="error")
        
        # Correlate with SuzieQ anomaly window
        syslog_search(keyword="LINK", start_time="2025-11-29T02:00:00Z", end_time="2025-11-29T03:00:00Z")
    """
    impl = ToolRegistry.get_tool("syslog_search")
    if impl is None:
        return {"success": False, "error": "syslog_search tool not registered"}
    
    result = await impl.execute(
        keyword=keyword,
        device_ip=device_ip,
        start_time=start_time,
        end_time=end_time,
        severity=severity,
        limit=limit,
    )
    
    return {
        "success": result.error is None,
        "error": result.error,
        "data": result.data,
        "metadata": result.metadata,
    }
```

---

## 5. Agent 集成

### 5.1 Deep Dive Workflow 增强

在 `config/prompts/workflows/deep_dive.yaml` 中添加 Syslog 搜索步骤：

```yaml
# 追加到 Deep Dive prompt
syslog_correlation: |
  当进行根因分析时，使用 syslog_search 搜索相关日志：
  
  1. **确定时间窗口**: 使用 suzieq_query 找到异常开始时间
  2. **搜索触发事件**: 
     ```
     syslog_search(
         keyword="DOWN|CHANGE|ERROR",
         device_ip="{anomaly_device}",
         start_time="{anomaly_start - 5min}",
         end_time="{anomaly_start + 5min}"
     )
     ```
  3. **关联分析**: 将日志事件与 SuzieQ 指标变化对照
  
  常见触发事件关键词：
  - 链路故障: LINK-DOWN, INTERFACE-DOWN, CARRIER-LOSS
  - BGP 事件: BGP-NEIGHBOR, ADJCHANGE, NOTIFICATION
  - OSPF 事件: OSPF-NEIGHBOR, ADJACENCY
  - 配置变更: CONFIG_CHANGE, CONFIGURATION, COMMIT
  - 硬件故障: MEMORY, CPU, TEMPERATURE, FAN
```

### 5.2 工具列表更新

```python
# src/olav/workflows/deep_dive.py 工具列表
micro_tools = [
    suzieq_query,
    suzieq_schema_search,
    syslog_search,       # ← 新增
    netconf_get_config,
    nornir_execute,
]
```

---

## 6. 厂商日志格式参考

### 6.1 无需解析，但便于理解

```
# Cisco IOS 格式
*Nov 29 10:30:45.123: %BGP-5-ADJCHANGE: neighbor 10.1.1.2 Down Interface flap
*Nov 29 10:30:45.456: %LINK-3-UPDOWN: Interface GigabitEthernet0/1, changed state to down

# Juniper 格式
Nov 29 10:30:45 R1 rpd[1234]: BGP_NEIGHBOR_STATE_CHANGED: 10.1.1.2 state Established -> Idle
Nov 29 10:30:45 R1 mib2d[5678]: SNMP_TRAP_LINK_DOWN: ifIndex 512, ifName ge-0/0/1

# Huawei 格式
Nov 29 2025 10:30:45 R1 %%01BGP/5/ADJCHANGE(l): Peer 10.1.1.2 state changed to Idle
Nov 29 2025 10:30:45 R1 %%01IFNET/4/LINK_STATE(l): GigabitEthernet0/0/1 status is DOWN

# Arista 格式
Nov 29 10:30:45 R1 Bgp: %BGP-3-NOTIFICATION: neighbor 10.1.1.2 Down
Nov 29 10:30:45 R1 Intf: %INTF-3-LINK_DOWN: Interface Ethernet1 is down
```

### 6.2 常用搜索关键词

| 场景 | 关键词 |
|------|--------|
| 链路故障 | `DOWN`, `UPDOWN`, `LINK`, `CARRIER` |
| BGP 问题 | `BGP`, `ADJCHANGE`, `NEIGHBOR`, `NOTIFICATION` |
| OSPF 问题 | `OSPF`, `ADJACENCY`, `NEIGHBOR` |
| 配置变更 | `CONFIG`, `COMMIT`, `CONFIGURATION` |
| 硬件问题 | `MEMORY`, `CPU`, `TEMPERATURE`, `FAN`, `POWER` |
| 认证问题 | `AUTH`, `LOGIN`, `FAILED`, `DENIED` |

---

## 7. 收益评估

### 7.1 定量收益

| 指标 | 改进前 | 改进后 |
|------|--------|--------|
| 根因定位时间 | 手动查设备日志 (~5-10 min) | 自动搜索 (~5 sec) |
| 多设备关联 | 逐台查看 | 单次查询 |
| 时间窗口搜索 | 需解析日志 | 原生支持 |

### 7.2 定性收益

- ✅ 填补**事件驱动诊断**的空白
- ✅ 完善漏斗式排错：宏观 → **事件** → 微观
- ✅ 减少人工干预（无需 SSH 到设备查日志）
- ✅ 增强 Deep Dive 递归诊断能力

### 7.3 复杂度成本

| 项目 | 工作量 |
|------|--------|
| rsyslog 容器 | 配置文件 ~30 行 |
| OpenSearch 索引 | ETL 脚本 ~50 行 |
| syslog_search 工具 | ~100 行 |
| Prompt 更新 | ~20 行 |
| **总计** | **~200 行代码 + 配置** |

---

## 8. 实施计划

### Phase 1: 基础设施 (0.5 天)
- [ ] 添加 rsyslog 容器到 docker-compose.yml
- [ ] 配置 rsyslog → OpenSearch
- [ ] 创建 syslog-raw 索引 + ILM 策略

### Phase 2: 工具实现 (0.5 天)
- [ ] 实现 `syslog_search` 工具
- [ ] 注册到 ToolRegistry
- [ ] 添加单元测试

### Phase 3: Agent 集成 (1 天)
- [ ] 更新 Deep Dive Workflow prompt
- [ ] 添加 syslog_search 到工具列表
- [ ] 编写集成测试

### Phase 4: 验证 (0.5 天)
- [ ] 端到端测试（模拟设备发送 syslog）
- [ ] 文档更新

---

## 9. 未来扩展

### 9.1 结构化解析（可选）

如需从日志中提取结构化字段（如 facility、mnemonic），可在 rsyslog 中添加 Grok 解析：

```conf
# 未来增强：解析 Cisco 格式
template(name="cisco-parsed" type="list") {
    # 提取 %FACILITY-SEVERITY-MNEMONIC
    property(name="msg" regex.expression="%([A-Z_]+)-([0-9])-([A-Z_]+):" ...)
}
```

### 9.2 异常检测（可选）

- 日志突增告警
- 关键词触发通知
- 与 Prometheus AlertManager 集成

### 9.3 语义搜索（可选）

- 向量化日志消息
- 使用 embedding 进行相似日志聚类
- 支持自然语言查询："昨晚有没有网络中断？"
