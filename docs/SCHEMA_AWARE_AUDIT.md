# Schema-Aware 架构审计报告

> **审计日期**: 2025-11-29
> **目标**: 识别违反 Schema-Aware 原则的硬编码，推进 LLM 完全智能化

## 核心原则

### Schema-Aware 设计理念

```
❌ 硬编码 120+ 工具/字段映射 → 维护噩梦
✅ 2 个通用工具 + Schema 索引 → LLM 动态发现
```

**架构目标**:
1. **零硬编码字段映射** - 所有字段信息从 Schema 索引动态获取
2. **LLM 语义理解** - 让 LLM 理解字段含义，而非维护映射表
3. **插件无感知** - NetBox 新增插件无需修改代码

### 数据流

```
用户查询 → LLM 意图分类 → Schema 搜索 → LLM 参数提取 → 工具执行
              ↓                ↓               ↓
         动态路由          动态发现         动态构建
```

---

## 🔴 高优先级问题 (P0)

### 1. DiffEngine 硬编码字段规则

**位置**: `src/olav/sync/diff_engine.py` (行 50-63)

```python
# ❌ 当前实现 - 硬编码
AUTO_CORRECT_FIELDS: ClassVar[dict[str, list[str]]] = {
    "interface": ["description", "mtu"],
    "device": ["serial_number", "software_version", "platform"],
    "ip_address": ["status", "dns_name"],
}

HITL_REQUIRED_FIELDS: ClassVar[dict[str, list[str]]] = {
    "interface": ["enabled", "mode", "tagged_vlans", "untagged_vlan"],
    "ip_address": ["address", "assigned_object"],
    ...
}
```

**问题**:
- NetBox 插件新增字段无法自动识别
- 维护成本高，容易遗漏

**修复方案**: 使用 LLM 判断字段安全性

```python
# ✅ Schema-Aware + LLM 方案
class LLMFieldClassifier:
    """使用 LLM 判断字段是否可以自动更正"""
    
    CLASSIFICATION_PROMPT = """
    分析以下 NetBox 字段变更，判断是否可以自动更正：
    
    实体类型: {entity_type}
    字段名称: {field_name}
    字段描述: {field_description}  # 从 netbox-schema-fields 获取
    当前值: {current_value}
    新值: {new_value}
    
    判断标准：
    1. 描述性字段 (description, comments) → 可自动更正
    2. 标识符字段 (serial, version) → 可自动更正
    3. 状态字段 (status, state) → 需要确认影响范围
    4. 关系字段 (assigned_object, site) → 需要 HITL
    5. 网络配置 (IP, VLAN, 路由) → 必须 HITL
    
    返回 JSON:
    {
        "auto_correctable": true/false,
        "hitl_required": true/false,
        "reason": "判断理由",
        "risk_level": "low/medium/high"
    }
    """
    
    async def classify_field(
        self,
        entity_type: str,
        field_name: str,
        current_value: Any,
        new_value: Any,
    ) -> FieldClassification:
        # 1. 从 netbox-schema-fields 获取字段元数据
        field_schema = await self.schema_loader.get_field_schema(
            entity_type, field_name
        )
        
        # 2. 调用 LLM 进行分类
        response = await self.llm.ainvoke([
            SystemMessage(content=self.CLASSIFICATION_PROMPT.format(
                entity_type=entity_type,
                field_name=field_name,
                field_description=field_schema.get("description", ""),
                current_value=current_value,
                new_value=new_value,
            ))
        ])
        
        return FieldClassification.model_validate_json(response.content)
```

---

### 2. Auto-Correct 规则硬编码

**位置**: `src/olav/sync/rules/auto_correct.py` (行 14-28)

```python
# ❌ 当前实现 - 硬编码转换函数
AUTO_CORRECT_RULES: dict[EntityType, dict[str, Callable[[Any], Any]]] = {
    EntityType.INTERFACE: {
        "description": lambda v: str(v) if v else "",
        "mtu": lambda v: int(v) if v else None,
    },
    EntityType.DEVICE: {
        "serial": lambda v: str(v) if v else "",
        "software_version": lambda v: str(v) if v else "",
    },
}
```

**修复方案**: LLM 驱动的值转换

```python
# ✅ LLM + Schema 方案
class LLMValueTransformer:
    """使用 LLM 根据 Schema 类型进行值转换"""
    
    async def transform_value(
        self,
        field_name: str,
        source_value: Any,
        target_schema: dict,
    ) -> Any:
        """
        根据目标 Schema 转换值。
        
        Args:
            field_name: 字段名
            source_value: 源值 (来自网络设备)
            target_schema: NetBox 字段 Schema
            
        Returns:
            转换后的值
        """
        # 从 Schema 获取目标类型
        target_type = target_schema.get("type", "string")
        field_format = target_schema.get("format")
        enum_values = target_schema.get("enum", [])
        
        # 简单类型直接转换
        if target_type == "integer":
            return int(source_value) if source_value else None
        elif target_type == "boolean":
            return source_value in (True, "true", "up", "active", 1)
        elif enum_values:
            # 使用 LLM 映射枚举值
            return await self._llm_map_enum(source_value, enum_values)
        else:
            return str(source_value) if source_value else ""
    
    async def _llm_map_enum(self, value: Any, enum_values: list) -> str:
        """使用 LLM 将网络值映射到 NetBox 枚举"""
        prompt = f"""
        将网络设备状态值映射到 NetBox 枚举值：
        
        输入值: {value}
        可选枚举: {enum_values}
        
        返回最匹配的枚举值（只返回值，无其他文字）
        """
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        return response.content.strip()
```

---

### 3. HITL 规则硬编码

**位置**: `src/olav/sync/rules/hitl_required.py` (行 12-50)

```python
# ❌ 当前实现
HITL_REQUIRED_RULES: dict[EntityType, set[str]] = {
    EntityType.INTERFACE: {
        "enabled", "mode", "tagged_vlans", "untagged_vlan", "lag", "existence",
    },
    EntityType.IP_ADDRESS: {
        "address", "assigned_object", "vrf", "existence",
    },
    ...
}
```

**修复方案**: 合并到 `LLMFieldClassifier`，使用统一的 LLM 判断

---

### 4. SuzieQ 唯一键硬编码

**位置**: `src/olav/tools/suzieq_tool.py` (行 251-257)

```python
# ❌ 当前实现
unique_keys = {
    "bgp": ["hostname", "peer", "afi", "safi"],
    "interfaces": ["hostname", "ifname"],
    "routes": ["hostname", "vrf", "prefix"],
}
```

**修复方案**: 从 SuzieQ Schema 动态获取

```python
# ✅ Schema-Aware 方案
async def _get_unique_keys(self, table: str) -> list[str]:
    """从 Schema 获取表的唯一键字段"""
    suzieq_schema = await self.schema_loader.load_suzieq_schema()
    table_schema = suzieq_schema.get(table, {})
    
    # SuzieQ Schema 中 key_fields 定义了唯一键
    key_fields = table_schema.get("key_fields", [])
    
    if key_fields:
        return key_fields
    
    # Fallback: 总是包含 hostname
    return ["hostname"]
```

---

### 5. Deep Dive OSI 层映射硬编码

**位置**: `src/olav/workflows/deep_dive.py` (行 484-489)

```python
# ❌ 当前实现
self.layer_tables: dict[str, list[str]] = {
    "L1": ["interfaces", "lldp"],
    "L2": ["macs", "vlan"],
    "L3": ["arpnd", "routes"],
    "L4": ["bgp", "ospfIf", "ospfNbr"],
}
```

**修复方案**: 使用 LLM 根据表描述推断 OSI 层

```python
# ✅ LLM + Schema 方案
class OSILayerClassifier:
    """使用 LLM 根据 SuzieQ 表描述推断 OSI 层"""
    
    async def classify_tables_by_layer(self) -> dict[str, list[str]]:
        """动态构建 OSI 层到表的映射"""
        suzieq_schema = await self.schema_loader.load_suzieq_schema()
        
        prompt = f"""
        根据以下 SuzieQ 表的描述，将它们分类到 OSI 层：
        
        {json.dumps({
            table: schema.get("description", "")
            for table, schema in suzieq_schema.items()
        }, indent=2, ensure_ascii=False)}
        
        返回 JSON 格式：
        {{
            "L1": ["表名列表 - 物理层：接口状态、链路"],
            "L2": ["表名列表 - 数据链路层：MAC、VLAN、STP"],
            "L3": ["表名列表 - 网络层：ARP、路由"],
            "L4": ["表名列表 - 传输层及以上：BGP、OSPF"]
        }}
        """
        
        response = await self.llm_json.ainvoke([HumanMessage(content=prompt)])
        return json.loads(response.content)
```

---

## 🟡 中优先级问题 (P1)

### 6. HITL 工具名硬编码

**位置**: `src/olav/main.py` (行 612)

```python
# ❌ 当前实现
hitl_required_tools = {"cli_tool", "netconf_tool", "nornir_tool", "netbox_api_call"}
```

**修复方案**: 移到配置文件

```yaml
# config/hitl_config.yaml
hitl_required_tools:
  - cli_tool
  - netconf_tool
  - nornir_tool
  - netbox_api_call

# 或者使用工具元数据
tools_metadata:
  cli_tool:
    requires_hitl: true
    write_operation: true
  suzieq_query:
    requires_hitl: false
    write_operation: false
```

---

### 7. 意图分类关键词 Fallback

**位置**: `src/olav/strategies/fast_path.py` (行 95-101)

```python
# ⚠️ 已标记为 FALLBACK，但仍需改进
INTENT_PATTERNS_FALLBACK: dict[str, list[str]] = {
    "netbox": ["netbox", "cmdb", "资产"],
    "suzieq": ["bgp", "ospf", "interface"],
    ...
}
```

**状态**: 可接受 - 主路径使用 `LLMIntentClassifier`，这只是无 LLM 时的降级方案

---

### 8. 优先实体列表

**位置**: `src/olav/etl/netbox_schema_etl.py` (行 31-42)

```python
PRIORITY_ENTITIES = [
    "Device", "Interface", "IPAddress", "VLAN", "VRF", "Prefix", ...
]
```

**修复方案**: 从 NetBox 动态获取高频使用的实体

```python
# ✅ 动态方案
async def get_priority_entities() -> list[str]:
    """从 NetBox 统计 API 调用频率，动态确定优先实体"""
    # 方案 1: 从配置文件读取
    # 方案 2: 统计 episodic memory 中的实体使用频率
    # 方案 3: 使用 LLM 根据用户场景推荐
    pass
```

---

## 🟢 已正确实现 (参考)

### SuzieQ Schema Search (正确示例)

```python
# src/olav/tools/suzieq_tool.py
class SuzieQSchemaSearchTool:
    """✅ 正确的 Schema-Aware 实现"""
    
    async def execute(self, query: str) -> ToolOutput:
        # 动态从 OpenSearch 加载 Schema
        suzieq_schema = await self.schema_loader.load_suzieq_schema()
        
        # 关键词匹配查找相关表
        matches = []
        for table, schema in suzieq_schema.items():
            if any(kw in table.lower() or kw in schema["description"].lower() 
                   for kw in query.lower().split()):
                matches.append({
                    "table": table,
                    "fields": schema["fields"],
                    "description": schema["description"],
                })
        
        return ToolOutput(source="schema", data=matches)
```

### LLMDiffEngine (正确示例)

```python
# src/olav/sync/llm_diff.py
class LLMDiffEngine:
    """✅ 正确的 LLM 驱动实现"""
    
    async def compare(self, netbox_data: dict, network_data: dict) -> list[DiffResult]:
        """使用 LLM 进行语义比较，无需硬编码字段映射"""
        
        prompt = f"""
        比较以下两个数据源，识别差异：
        
        NetBox (SSOT):
        {json.dumps(netbox_data, indent=2)}
        
        Network (实际状态):
        {json.dumps(network_data, indent=2)}
        
        对于每个差异，返回：
        - field: 字段名
        - netbox_value: NetBox 中的值
        - network_value: 网络设备中的值
        - severity: INFO/WARNING/CRITICAL
        - auto_correctable: 是否可以自动更正
        """
        
        # LLM 理解语义，自动处理字段映射
        response = await self.llm.ainvoke([...])
        return self._parse_diff_response(response)
```

---

## 重构路线图

### Phase 1: 配置外化 (1-2 天)

1. 将 `AUTO_CORRECT_FIELDS` / `HITL_REQUIRED_FIELDS` 移到 `config/rules/sync_rules.yaml`
2. 将 `hitl_required_tools` 移到 `config/hitl_config.yaml`
3. 将 `PRIORITY_ENTITIES` 移到 `config/netbox_config.yaml`

### Phase 2: Schema 动态化 (2-3 天)

1. 修改 `SuzieQTool._get_unique_keys()` 从 Schema 读取
2. 添加 `schema_loader.get_field_schema()` 方法
3. 扩展 `netbox-schema-fields` 索引，包含字段安全性元数据

### Phase 3: LLM 智能化 (3-5 天)

1. 实现 `LLMFieldClassifier` 替代硬编码规则
2. 实现 `LLMValueTransformer` 替代转换函数
3. 实现 `OSILayerClassifier` 动态构建层映射

### Phase 4: 验证与清理 (1-2 天)

1. 添加单元测试验证动态行为
2. 删除所有硬编码字典
3. 更新文档

---

## 验收标准

- [ ] `grep -r "HARDCODED\|硬编码" src/` 返回 0 结果
- [ ] 新增 NetBox 插件字段无需修改代码
- [ ] SuzieQ 新增表自动可用
- [ ] LLM 可以解释字段分类决策
- [ ] 所有规则可通过配置文件覆盖

---

## 参考资料

- [Schema-Aware 设计原则](/.github/copilot-instructions.md#schema-aware-tool-design)
- [LLMDiffEngine 实现](../src/olav/sync/llm_diff.py)
- [SuzieQ Schema ETL](../src/olav/etl/suzieq_schema_etl.py)
- [NetBox Schema ETL](../src/olav/etl/netbox_schema_etl.py)
