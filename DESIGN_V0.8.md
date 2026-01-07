# OLAV v0.8 详细设计文档 (DeepAgents Native)

> **文档版本**: 2.4  
> **创建日期**: 2026-01-07  
> **核心理念**: 参考 Claude Code Skills 模式，三层知识架构 (Skills / Knowledge / Tools)

---

## 目录

1. [设计哲学](#1-设计哲学)
2. [三层知识架构](#2-三层知识架构)
3. [OLAV.md 核心指令](#3-olavmd-核心指令)
4. [Skills 策略层](#4-skills-策略层)
5. [Knowledge 知识层](#5-knowledge-知识层)
6. [Tools 能力层](#6-tools-能力层)
7. [DeepAgents 框架集成](#7-deepagents-框架集成)
8. [Agentic 自学习机制](#8-agentic-自学习机制)
9. [测试策略](#9-测试策略)
10. [分阶段开发路线图](#10-分阶段开发路线图)
11. [文件结构规划](#11-文件结构规划)

---

## 1. 设计哲学

### 1.1 核心原则：参考 Claude Code Skills

```
Claude Code 的设计:
~/.claude/CLAUDE.md     → 全局指令
project/.claude/        → 项目指令
└── commands/           → 自定义命令

OLAV 的类比设计:
OLAV.md                 → 核心身份与规则
skills/                 → 任务策略 (HOW)
knowledge/              → 事实知识 (WHAT)
tools/                  → 能力定义 (CAN)
```

### 1.2 关键洞察

**Skills ≠ Tools**

| 概念 | 定义 | 格式 | Agent 权限 |
|------|------|------|-----------|
| **Skills** | 怎么做 (策略/SOP) | Markdown | 读 + 写 |
| **Knowledge** | 是什么 (事实/记忆) | Markdown | 读 + 写 |
| **Tools** | 能做什么 (能力) | txt/yaml/py | 读 + 部分写 |

Skills 是**方法论**，指导 Agent 如何使用已有工具，而不是定义新工具。

### 1.3 愿景

```
┌─────────────────────────────────────────────────────────────┐
│                   OLAV v0.8 核心愿景                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  用户使用:                                                   │
│  1. 自然语言描述需求                                         │
│  2. Agent 读取 skills/ 知道如何做                            │
│  3. Agent 读取 knowledge/ 了解环境上下文                     │
│  4. Agent 使用 tools/ 中定义的能力执行                       │
│                                                             │
│  用户扩展:                                                   │
│  ├── 添加新策略 → 写 skills/xxx.md                          │
│  ├── 添加新知识 → 写 knowledge/xxx.md                       │
│  ├── 添加新命令 → 编辑 tools/commands/*.txt                 │
│  └── 添加新 API → 放入 tools/apis/*.yaml                    │
│                                                             │
│  Agent 自学习:                                               │
│  ├── 学习新策略 → 更新 skills/                               │
│  ├── 记录新知识 → 更新 knowledge/                            │
│  └── 发现新命令 → 更新 tools/commands/                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 三层知识架构

### 2.1 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                     OLAV 知识架构                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  OLAV.md (入口)                                                 │
│  └── 核心身份、安全规则、基本原则                                │
│                                                                 │
│  ═══════════════════════════════════════════════════════════   │
│                                                                 │
│  skills/                     HOW - 策略方法                      │
│  ├── quick-query.md          快速查询的执行策略                  │
│  ├── deep-analysis.md        深度分析的执行策略                  │
│  └── device-inspection.md    设备巡检的执行策略                  │
│                                                                 │
│  ═══════════════════════════════════════════════════════════   │
│                                                                 │
│  knowledge/                  WHAT - 事实知识                     │
│  ├── aliases.md              设备别名 (核心交换机=10.1.1.1)      │
│  ├── conventions.md          命名约定 (CS-* 表示核心设备)        │
│  └── solutions/              历史案例库                          │
│      ├── crc-errors.md                                          │
│      └── ospf-flapping.md                                       │
│                                                                 │
│  ═══════════════════════════════════════════════════════════   │
│                                                                 │
│  data/olav.db                CAN - 能力数据库 (DuckDB)           │
│  └── capabilities 表         CLI 命令 + API 端点统一存储         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 三层定义

| 层 | 目录/位置 | 回答的问题 | 格式 | Agent 权限 |
|----|----------|-----------|------|-----------|
| **Skills** | `skills/` | "遇到这类任务怎么做？" | Markdown | 读 + 写 |
| **Knowledge** | `knowledge/` | "这个东西是什么？" | Markdown | 读 + 写 |
| **Tools** | `data/olav.db` | "我能调用什么？" | DuckDB | 读 (通过工具) |

### 2.3 层间关系

```
用户: "检查核心交换机的接口状态"
        │
        ▼
┌─ knowledge/aliases.md ─────────────────────────────────┐
│  "核心交换机" = 10.1.1.1, platform: cisco_ios          │
└────────────────────────────────────────────────────────┘
        │
        ▼
┌─ skills/quick-query.md ────────────────────────────────┐
│  快速查询策略:                                          │
│  1. 不需要 write_todos                                 │
│  2. 使用 search_capabilities 查找命令                  │
│  3. 执行 1-2 条命令返回                                │
└────────────────────────────────────────────────────────┘
        │
        ▼
┌─ search_capabilities("interface", platform="cisco_ios")┐
│  → "show interface*" (支持通配符扩展)                   │
└────────────────────────────────────────────────────────┘
        │
        ▼
    nornir_execute(10.1.1.1, "show interfaces status")
```

---

## 3. OLAV.md 核心指令

类似 Claude Code 的 `CLAUDE.md`，定义 Agent 的核心身份和规则。

### 3.1 文件位置

```
项目根目录/OLAV.md
```

### 3.2 内容结构

```markdown
# OLAV - Network AI Operations Assistant

## 身份
你是 OLAV，一个网络运维 AI 助手。你帮助用户查询网络设备状态、
分析故障、执行巡检。

## 核心原则
1. 安全第一：只执行白名单中的命令
2. 先理解再行动：复杂任务使用 write_todos 规划
3. 学习积累：记录有价值的知识和解决方案

## 知识获取
启动时读取:
- skills/ 了解如何执行各类任务
- knowledge/aliases.md 了解设备别名
- tools/commands/ 了解可用命令

## 安全规则
- ✅ 可执行: show, display, get (只读命令)
- ⚠️ 需审批: configure, set (配置命令)
- ❌ 禁止: reload, erase, format (危险命令)

## 学习行为
当你学到新知识时:
- 设备别名 → 更新 knowledge/aliases.md
- 新的排查方法 → 更新 skills/*.md
- 成功案例 → 保存到 knowledge/solutions/
- 新命令 → 更新 tools/commands/*.txt (仅只读命令)
```

---

## 4. Skills 策略层

### 4.1 什么是 Skill

**Skill = Markdown 格式的任务策略**，告诉 Agent 遇到某类任务时应该怎么做。

⚠️ **重要**: Skill 不是工具定义，而是**使用工具的方法**。

### 4.2 Skill 示例

#### skills/quick-query.md

```markdown
# Quick Query (快速查询)

## 适用场景
- 查询设备接口状态
- 查询路由表
- 查询 ARP/MAC 表
- 简单的状态检查

## 识别标志
用户问题包含: "查一下"、"看看"、"状态"、"是否正常"

## 执行策略
1. 不需要 write_todos，直接执行
2. 从 knowledge/aliases.md 解析设备别名
3. 从 tools/commands/ 选择合适的命令
4. 执行 1-2 条命令即可
5. 结果简洁，只返回关键信息

## 示例

### 接口状态
触发: "R1 的 Gi0/1 状态"
命令: show interfaces GigabitEthernet0/1
提取: up/down、速率、错误计数

### IP/MAC 定位
触发: "10.1.1.100 在哪个端口"
流程:
1. show arp | include 10.1.1.100 → 获取 MAC
2. show mac address-table address <mac> → 获取端口
```

#### skills/deep-analysis.md

```markdown
# Deep Analysis (深度分析)

## 适用场景
- 网络故障排查
- 性能问题分析
- 路径追踪
- 根因定位

## 识别标志
用户问题包含: "为什么"、"排查"、"分析"、"故障"、"不通"

## 执行策略
1. 使用 write_todos 分解问题
2. 判断问题类型，选择分析方向
3. 委派给合适的 Subagent
4. 综合分析，给出结论和建议

## Subagent 选择

### macro-analyzer (宏观分析)
适用于:
- "哪个节点出了问题"
- "路径上哪里丢包"
- "影响范围有多大"
- 需要查看拓扑关系

### micro-analyzer (微观分析)
适用于:
- "为什么这个端口不通"
- "接口有错误"
- 需要逐层排查具体设备

### 组合使用
1. 先用 macro-analyzer 确定故障域
2. 再用 micro-analyzer 定位具体原因

## TCP/IP 逐层排错框架 (微观)
1. **物理层**: 端口状态、光功率、CRC 错误
2. **数据链路层**: VLAN、MAC 表、STP 状态
3. **网络层**: IP 地址、路由表、ARP
4. **传输层**: ACL、NAT、端口过滤
5. **应用层**: DNS、服务可达性
```

#### skills/device-inspection.md

```markdown
# Device Inspection (设备巡检)

## 适用场景
- 定期健康检查
- 上线前检查
- 故障后复查

## 执行策略
1. 使用 write_todos 列出检查项
2. 按模板逐项执行
3. 生成结构化报告
4. 标记异常项

## 巡检模板

### 系统健康
- [ ] show version (运行时间、版本)
- [ ] show processes cpu history (CPU 趋势)
- [ ] show memory statistics (内存使用)

### 接口状态
- [ ] show interfaces status (端口状态)
- [ ] show interfaces counters errors (错误计数)

### 路由状态
- [ ] show ip route summary (路由汇总)
- [ ] show ip ospf neighbor (OSPF 邻居)
- [ ] show ip bgp summary (BGP 邻居)

## 报告格式
使用表格展示每项检查结果:
| 检查项 | 状态 | 详情 |
|--------|------|------|
| CPU | ✅ 正常 | 平均 15% |
| 内存 | ⚠️ 警告 | 使用 85% |
```

### 4.3 Agent 如何使用 Skills

```
1. Agent 启动时读取 skills/ 目录，了解所有可用策略
2. 收到用户请求后，根据"识别标志"匹配适合的 Skill
3. 按 Skill 中的"执行策略"完成任务
4. 如果任务成功且有新发现，可更新 Skill 添加新模式
```

### 4.4 Skills 禁用机制

支持两种方式禁用 Skill，无需删除文件：

#### 方式一：Frontmatter 元数据

```markdown
---
enabled: false
reason: "已被 quick-query-v2.md 替代"
deprecated_at: 2026-01-07
---
# Quick Query (旧版)

## 适用场景
...
```

#### 方式二：文件命名约定

```
skills/
├── quick-query.md              # ✅ 启用
├── deep-analysis.md            # ✅ 启用
├── _device-inspection.md       # ❌ 禁用 (_ 前缀)
├── experimental.draft.md       # ❌ 禁用 (.draft 后缀)
└── archived/                   # ❌ 禁用 (归档目录)
    └── legacy-query.md
```

#### Agent 加载逻辑

```python
def load_skills(skills_dir: Path) -> list[Skill]:
    skills = []
    for md_file in skills_dir.glob("*.md"):
        # 跳过 _ 前缀和 .draft 后缀
        if md_file.name.startswith("_") or ".draft" in md_file.name:
            continue
        
        content = md_file.read_text()
        
        # 解析 frontmatter
        if content.startswith("---"):
            fm = parse_frontmatter(content)
            if fm.get("enabled") == False:
                continue
        
        skills.append(parse_skill(content))
    
    return skills
```

#### Knowledge 同样适用

```
knowledge/
├── aliases.md                  # ✅ 启用
├── conventions.md              # ✅ 启用
├── _old-topology.md            # ❌ 禁用
└── solutions/
    ├── crc-errors.md           # ✅ 启用
    └── _outdated-fix.md        # ❌ 禁用
```

---

## 5. Knowledge 知识层

### 5.1 什么是 Knowledge

**Knowledge = 事实性信息**，Agent 需要了解的环境上下文。

### 5.2 Knowledge 示例

#### knowledge/aliases.md

```markdown
# 设备别名

Agent 在执行命令前应查阅此文件，将用户使用的别名转换为实际值。

| 别名 | 实际值 | 类型 | 平台 | 备注 |
|------|--------|------|------|------|
| 核心交换机 | 10.1.1.1 | device | cisco_ios | 数据中心核心 |
| 出口路由器 | 10.1.1.254 | device | cisco_ios | 互联网出口 |
| 上海专线 | GigabitEthernet0/0/1 | interface | - | R1 上的专线接口 |
| 办公网 | VLAN 100 | vlan | - | 办公区域 |

## 使用说明
- 当用户提到这些别名时，自动替换为实际值
- 如果用户使用了新的别名，询问含义后更新此文件
```

#### knowledge/conventions.md

```markdown
# 网络命名约定

## 设备命名
- `CS-<城市>-<编号>`: 核心交换机 (Core Switch)
- `DS-<城市>-<编号>`: 汇聚交换机 (Distribution Switch)  
- `AS-<楼层>-<编号>`: 接入交换机 (Access Switch)
- `R-<城市>-<编号>`: 路由器

## VLAN 规划
- VLAN 1-99: 管理用
- VLAN 100-199: 办公区
- VLAN 200-299: 生产区
- VLAN 300-399: DMZ

## IP 规划
- 10.1.0.0/16: 总部
- 10.2.0.0/16: 上海分部
- 10.3.0.0/16: 北京分部
```

#### knowledge/solutions/crc-errors.md

```markdown
# 案例: CRC 错误导致网络抖动

## 问题描述
用户反映网络时断时续，ping 丢包严重。

## 排查过程
1. show interfaces → 发现 Gi0/1 有大量 CRC 错误
2. show interfaces transceiver → RX power -18 dBm (偏低)
3. 检查光纤连接 → 发现光模块老化

## 根因
光模块老化，接收功率下降导致 CRC 错误。

## 解决方案
更换光模块。

## 关键命令
- show interfaces | include CRC|errors
- show interfaces transceiver detail

## 标签
#接口 #CRC #光模块 #物理层
```

---

## 6. Tools 能力层 (文件即真理)

### 6.1 设计理念

**核心思想**: 文件是唯一真理源，DuckDB 只是运行时缓存。

```
imports/                          ← 唯一真理源 (Git 版本控制)
├── commands/                     
│   ├── cisco_ios.txt            # ✅ 启用
│   ├── _huawei_vrp.txt          # ❌ 禁用 (_ 前缀)
│   └── juniper_junos.txt        
└── apis/                        
    ├── netbox.yaml              # OpenAPI 原生格式
    └── _zabbix.yaml             # ❌ 禁用
            ↓
      olav reload                # 手动刷新
            ↓
        DuckDB                   # 运行时缓存，可删除重建
```

**与 Skills/Knowledge 一致的模式**:

| 层 | 真理源 | 格式 | 禁用方式 |
|----|--------|------|----------|
| Skills | `skills/*.md` | Markdown | `_` 前缀 |
| Knowledge | `knowledge/*.md` | Markdown | `_` 前缀 |
| **Capabilities** | `imports/**` | txt/yaml | `_` 前缀 |

**用户操作**:

| 操作 | 方式 |
|------|------|
| 添加平台 | 创建 `imports/commands/arista.txt` |
| 禁用平台 | 重命名为 `_arista.txt` |
| 删除平台 | 删除文件 |
| 生效 | `olav reload` |

### 6.2 Capabilities 表设计

```sql
-- DuckDB: data/olav.db (运行时缓存，可删除重建)

CREATE TABLE capabilities (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,           -- 'command' | 'api'
    platform TEXT NOT NULL,       -- 'cisco_ios' | 'huawei_vrp' | 'netbox'
    name TEXT NOT NULL,           -- 'show interface*' | '/dcim/devices/'
    method TEXT,                  -- NULL (命令) | 'GET' | 'POST' | 'PATCH'
    description TEXT,             -- 可选描述
    parameters TEXT,              -- JSON: API 参数定义
    is_write BOOLEAN DEFAULT FALSE,  -- 是否需要 HITL 审批
    source_file TEXT NOT NULL     -- 来源文件，用于重建追溯
);

-- 索引优化搜索
CREATE INDEX idx_cap_type ON capabilities(type);
CREATE INDEX idx_cap_platform ON capabilities(platform);
CREATE INDEX idx_cap_name ON capabilities(name);
```

**注意**: 没有 `enabled` 字段，因为禁用通过文件名 `_` 前缀控制，禁用的文件不会被加载。

### 6.3 示例数据

```sql
-- CLI 命令 (使用通配符简化)
INSERT INTO capabilities (type, platform, name, is_write) VALUES
('command', 'cisco_ios', 'show version', FALSE),
('command', 'cisco_ios', 'show interface*', FALSE),      -- 匹配 show interface Gi0/1
('command', 'cisco_ios', 'show ip route*', FALSE),
('command', 'cisco_ios', 'show ip bgp*', FALSE),
('command', 'cisco_ios', 'show ip ospf*', FALSE),
('command', 'cisco_ios', 'show vlan*', FALSE),
('command', 'cisco_ios', 'show mac address-table*', FALSE),
('command', 'cisco_ios', 'show arp*', FALSE),
('command', 'cisco_ios', 'ping*', FALSE),
('command', 'cisco_ios', 'traceroute*', FALSE),
('command', 'cisco_ios', 'configure terminal', TRUE),    -- 需要 HITL

('command', 'huawei_vrp', 'display version', FALSE),
('command', 'huawei_vrp', 'display interface*', FALSE),
('command', 'huawei_vrp', 'display ip routing-table*', FALSE),

-- API 端点
('api', 'netbox', '/dcim/devices/', 'GET', '查询设备列表',
    '{"name": "str?", "site": "str?", "role": "str?"}', FALSE),
('api', 'netbox', '/dcim/interfaces/', 'GET', '查询接口列表',
    '{"device": "str?", "name": "str?"}', FALSE),
('api', 'netbox', '/dcim/devices/{id}/', 'PATCH', '更新设备信息',
    '{"status": "str?", "comments": "str?"}', TRUE),

('api', 'zabbix', '/api_jsonrpc.php', 'POST', '获取告警列表',
    '{"method": "problem.get", "params": {...}}', FALSE);
```

### 6.4 search_capabilities 工具 (Schema Aware)

```python
@tool
def search_capabilities(
    query: str,
    type: Literal["command", "api", "all"] = "all",
    platform: str | None = None,
    limit: int = 20
) -> list[dict]:
    """搜索可用的 CLI 命令或 API 端点
    
    在能力库中搜索匹配的命令或 API。支持自然语言查询，
    LLM 可以用语义描述需求，工具返回匹配的能力。
    
    Args:
        query: 搜索关键词 (如 "接口状态", "bgp", "设备列表")
        type: 能力类型
            - "command": 只搜索 CLI 命令
            - "api": 只搜索 API 端点
            - "all": 搜索全部
        platform: 限定平台 (cisco_ios, huawei_vrp, netbox, zabbix)
        limit: 返回结果数量限制
    
    Returns:
        匹配的能力列表，每项包含:
        - type: command | api
        - platform: 平台名称
        - name: 命令或端点 (支持通配符)
        - method: HTTP 方法 (仅 API)
        - description: 描述 (如有)
        - parameters: 参数定义 (仅 API)
        - is_write: 是否需要 HITL 审批
    
    Examples:
        # 查找接口相关命令
        search_capabilities("interface", type="command", platform="cisco_ios")
        # 返回: [{"name": "show interface*", "is_write": false}, ...]
        
        # 查找 NetBox 设备 API
        search_capabilities("设备", type="api", platform="netbox")
        # 返回: [{"name": "/dcim/devices/", "method": "GET", ...}, ...]
    """
    import duckdb
    
    conn = duckdb.connect("data/olav.db", read_only=True)
    
    sql = """
        SELECT type, platform, name, method, description, parameters, is_write
        FROM capabilities
        WHERE name ILIKE ? OR description ILIKE ? OR platform ILIKE ?
    """
    pattern = f"%{query}%"
    params = [pattern, pattern, pattern]
    
    if type != "all":
        sql += " AND type = ?"
        params.append(type)
    
    if platform:
        sql += " AND platform = ?"
        params.append(platform)
    
    sql += f" LIMIT {limit}"
    
    results = conn.execute(sql, params).fetchall()
    columns = ["type", "platform", "name", "method", "description", "parameters", "is_write"]
    
    return [dict(zip(columns, row)) for row in results]
```

### 6.5 命令匹配逻辑

```python
def is_command_allowed(command: str, platform: str) -> bool:
    """检查命令是否在白名单中
    
    匹配规则:
    1. 精确匹配: "show version" 匹配 "show version"
    2. 通配符匹配: "show interface*" 匹配 "show interface GigabitEthernet0/1"
    """
    import duckdb
    
    conn = duckdb.connect("data/olav.db", read_only=True)
    cmd_lower = command.lower().strip()
    
    # 获取该平台所有命令模式
    patterns = conn.execute("""
        SELECT name FROM capabilities 
        WHERE type = 'command' AND platform = ?
    """, [platform]).fetchall()
    
    for (pattern,) in patterns:
        pattern = pattern.lower().strip()
        if pattern.endswith("*"):
            # 通配符匹配
            prefix = pattern[:-1]
            if cmd_lower.startswith(prefix):
                return True
        else:
            # 精确匹配
            if cmd_lower == pattern:
                return True
    
    return False
```

### 6.6 api_call 元工具

```python
@tool
def api_call(
    system: str,
    method: str,
    endpoint: str,
    params: dict | None = None,
    body: dict | None = None
) -> dict:
    """调用外部 API 系统
    
    使用前请先调用 search_capabilities 了解可用端点。
    
    Args:
        system: API 系统名 (netbox, zabbix)
        method: HTTP 方法 (GET, POST, PUT, PATCH, DELETE)
        endpoint: API 端点路径 (如 /dcim/devices/)
        params: URL 查询参数
        body: 请求体 (POST/PUT/PATCH)
    
    Returns:
        API 响应数据
    
    Examples:
        # 查询设备列表
        api_call("netbox", "GET", "/dcim/devices/", params={"name": "R1"})
        
        # 更新设备状态 (需要 HITL 审批)
        api_call("netbox", "PATCH", "/dcim/devices/1/", body={"status": "active"})
    """
```

### 6.7 数据管理

**唯一命令**: `olav reload`

```bash
# 从 imports/ 目录重建 DuckDB 缓存
olav reload

# 预览变更 (不实际执行)
olav reload --dry-run

# 验证文件格式
olav validate
```

#### reload 逻辑

```python
def reload_capabilities(imports_dir: Path = Path("imports")):
    """从文件重建能力数据库
    
    1. 清空 capabilities 表
    2. 扫描 imports/commands/*.txt (跳过 _ 前缀)
    3. 扫描 imports/apis/*.yaml (跳过 _ 前缀)
    4. 解析并插入 DuckDB
    """
    conn = duckdb.connect("data/olav.db")
    conn.execute("DELETE FROM capabilities")
    
    # 加载命令文件
    for txt_file in (imports_dir / "commands").glob("*.txt"):
        if txt_file.name.startswith("_"):
            continue  # 跳过禁用文件
        platform = txt_file.stem  # cisco_ios.txt → cisco_ios
        load_commands(conn, txt_file, platform)
    
    # 加载 API 文件
    for yaml_file in (imports_dir / "apis").glob("*.yaml"):
        if yaml_file.name.startswith("_"):
            continue
        platform = yaml_file.stem  # netbox.yaml → netbox
        load_openapi(conn, yaml_file, platform)
    
    conn.close()
    print(f"Reloaded {count} capabilities")
```

#### 命令文件格式 (txt)

```txt
# imports/commands/cisco_ios.txt
# 每行一条命令，支持通配符和注释

# === 基础信息 ===
show version
show inventory

# === 接口相关 ===
show interface*
show ip interface brief

# === 路由相关 ===
show ip route*
show ip bgp*
show ip ospf*

# === 配置命令 (需要 HITL，用 ! 前缀标记) ===
!configure terminal
!write memory
```

#### API 文件格式 (OpenAPI YAML)

```yaml
# imports/apis/netbox.yaml
# 标准 OpenAPI 3.0 格式，额外支持 x-olav 扩展

openapi: "3.0.0"
info:
  title: NetBox API
  version: "3.0"
paths:
  /dcim/devices/:
    get:
      summary: 查询设备列表
      x-olav-write: false  # 可选: 标记是否需要 HITL
  /dcim/devices/{id}/:
    patch:
      summary: 更新设备信息
      x-olav-write: true   # 需要 HITL 审批
```

### 6.8 审计日志表

```sql
CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    thread_id TEXT NOT NULL,
    device TEXT NOT NULL,
    command TEXT NOT NULL,
    output TEXT,
    success BOOLEAN NOT NULL,
    duration_ms INTEGER,
    user TEXT
);

CREATE INDEX idx_audit_thread ON audit_logs(thread_id);
CREATE INDEX idx_audit_device ON audit_logs(device);
```

**注意**: 不使用命令缓存，始终获取最新数据。网络状态变化快，缓存可能导致误判。

### 6.9 Nornir 执行策略 (不重复造轮子)

**原则**: 错误处理、超时控制、并发策略全部使用 Nornir 原生机制。

#### Nornir 配置

```yaml
# config/nornir/config.yaml
runner:
  plugin: threaded
  options:
    num_workers: 20        # 并发执行数

inventory:
  plugin: SimpleInventory
  options:
    host_file: "config/nornir/hosts.yaml"

# 连接参数 (全局默认)
connection_options:
  netmiko:
    extras:
      timeout: 60          # 连接超时
      auth_timeout: 30     # 认证超时
      banner_timeout: 30   # Banner 超时
      conn_timeout: 30     # TCP 连接超时
```

#### 错误处理

```python
from nornir_utils.plugins.functions import print_failed_hosts

def execute_with_error_handling(nr: Nornir, task, *args, **kwargs):
    """使用 Nornir 原生错误处理"""
    result = nr.run(task=task, *args, **kwargs)
    
    # Nornir 自动收集失败主机
    if result.failed:
        failed_hosts = list(result.failed_hosts.keys())
        for host in failed_hosts:
            error = result[host].exception
            log.error(f"{host}: {error}")
    
    return result
```

#### 超时控制

```python
from nornir_netmiko.tasks import netmiko_send_command

def send_command_with_timeout(task, command: str, timeout: int = 30):
    """使用 Netmiko 原生超时"""
    return task.run(
        task=netmiko_send_command,
        command_string=command,
        read_timeout=timeout,      # 读取超时
        cmd_verify=True,           # 命令确认
    )
```

#### 并发控制

```python
from nornir import InitNornir
from nornir.core.filter import F

# 按需调整并发数
nr = InitNornir(
    runner={"plugin": "threaded", "options": {"num_workers": 10}}
)

# 或使用过滤器限制范围
core_devices = nr.filter(F(role="core"))
result = core_devices.run(task=some_task)
```

#### 重试机制

```python
from nornir_utils.plugins.tasks import retry

@retry(num_retries=3, retry_delay=5)
def robust_command(task, command: str):
    """Nornir 原生重试装饰器"""
    return task.run(
        task=netmiko_send_command,
        command_string=command,
    )
```

---

## 7. DeepAgents 框架集成

> **核心定位**: OLAV 完全构建于 DeepAgents 框架之上，充分利用其原生能力，避免重复造轮子。

### 7.1 Agent Harness 内置能力

DeepAgents 提供了完整的 Agent 运行时环境，OLAV 直接利用以下内置能力：

| 能力 | DeepAgents 实现 | OLAV 应用场景 |
|------|----------------|--------------|
| **write_todos** | 任务分解与追踪 | 深度分析时自动规划诊断步骤 |
| **Filesystem** | ls/read/write/edit/glob/grep | 读写 Skills/Knowledge/Tools 文件 |
| **Subagent (task)** | 上下文隔离的子任务委派 | config-analyzer, topology-explorer |
| **Large Result Eviction** | >20k tokens 自动写入文件 | 处理 `show running-config` 等大输出 |
| **History Summarization** | 自动压缩长对话 | 长时间排查会话保持上下文 |

### 7.2 HITL (Human-in-the-Loop) 机制

DeepAgents 通过 `interrupt_on` 参数原生支持 HITL：

```python
from deepagents import create_deep_agent

# HITL 配置 - 写操作需要人工审批
HITL_TOOLS = [
    "nornir_execute",      # 任何设备写操作
    "write_file",          # 文件写入
    "edit_file",           # 文件编辑
]

agent = create_deep_agent(
    model=llm,
    tools=all_tools,
    system_prompt=OLAV_SYSTEM_PROMPT,
    interrupt_on=HITL_TOOLS,  # 遇到这些工具时暂停等待审批
    checkpointer=checkpointer,  # 状态持久化，支持中断恢复
)
```

**工作流程**:
1. Agent 调用 `nornir_execute` 准备执行写命令
2. DeepAgents 自动暂停，返回 interrupt 状态
3. 前端展示待执行命令，等待用户确认
4. 用户批准后，使用 `Command(resume=...)` 继续执行

### 7.3 Checkpointer 状态持久化

**MVP 阶段使用内存存储，持久化功能延后**：

```python
from langgraph.checkpoint.memory import MemorySaver

# MVP: 使用内存存储 (简单可靠)
checkpointer = MemorySaver()

# 未来 (Phase 5+): 考虑 PostgreSQL 持久化
# from langgraph.checkpoint.postgres import PostgresSaver
# checkpointer = PostgresSaver.from_conn_string(POSTGRES_URL)
```

**当前支持**:
- ✅ HITL 中断期间状态保持
- ✅ 单次会话内的上下文保持

**延后功能**:
- ⏳ 跨会话恢复 (需要持久化)
- ⏳ 长时间任务断点续传

### 7.4 Storage Backend 策略 (CompositeBackend)

DeepAgents 支持 CompositeBackend 实现路径级别的存储策略：

```
┌─────────────────────────────────────────────────────────────┐
│                    CompositeBackend                          │
│                                                             │
│  路径                    → 后端                   → 特性     │
│  ───────────────────────────────────────────────────────────│
│  /skills/*              → StoreBackend (持久化)  → Agent 可写│
│  /knowledge/*           → StoreBackend (持久化)  → Agent 可写│
│  /tools/commands/       → StoreBackend (持久化)  → Agent 可写│
│  /tools/apis/           → StoreBackend (持久化)  → Agent 只读│
│  /scratch/*             → StateBackend (临时)    → 会话内有效│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**关键设计**: Agent 对 `skills/`, `knowledge/`, `tools/commands/` 有写权限，实现自学习。

### 7.5 Subagent 简化设计 (宏观/微观)

**设计原则**: 快速查询不需要 Subagent，故障分析需要。

```python
from deepagents.middleware.subagents import SubAgentMiddleware

subagent_middleware = SubAgentMiddleware(
    subagents=[
        {
            "name": "macro-analyzer",
            "description": "宏观分析: 拓扑、路径、端到端连通性",
            "system_prompt": """你是网络宏观分析专家。
            
你的职责:
1. 分析网络拓扑 (LLDP/CDP/BGP 邻居)
2. 追踪数据路径 (traceroute, 路由表)
3. 检查端到端连通性
4. 识别故障域 (哪个区域/设备有问题)

工作方式: 从全局视角入手，逐步缩小范围。""",
            "tools": ["nornir_execute", "search_capabilities", "api_call"],
        },
        {
            "name": "micro-analyzer", 
            "description": "微观分析: TCP/IP 各层逐级排错",
            "system_prompt": """你是网络微观分析专家，按 TCP/IP 分层排错。
            
排错顺序 (从下往上):
1. **物理层**: 端口状态、光功率、CRC 错误
2. **数据链路层**: VLAN、MAC 表、STP 状态
3. **网络层**: IP 地址、路由表、ARP
4. **传输层**: ACL、NAT、端口过滤
5. **应用层**: DNS、服务可达性

工作方式: 从物理层开始，逐层向上排查。""",
            "tools": ["nornir_execute", "search_capabilities"],
        },
    ]
)
```

**使用场景**:

| 任务类型 | 是否需要 Subagent | 说明 |
|----------|-----------------|------|
| 快速查询 | ❌ 不需要 | 主 Agent 直接执行 1-2 条命令 |
| 设备巡检 | ❌ 不需要 | 主 Agent 按模板执行 |
| 故障分析 | ✅ 需要 | 委派 macro/micro 分析 |

**委派策略** (在 `skills/deep-analysis.md` 中定义):

```markdown
## 故障分析委派策略

### 何时使用 macro-analyzer
- "哪个节点出了问题"
- "路径上哪里丢包"
- "影响范围有多大"
- 需要查看拓扑关系

### 何时使用 micro-analyzer  
- "为什么这个端口不通"
- "接口有错误"
- 需要逐层排查具体设备

### 组合使用
1. 先用 macro-analyzer 确定故障域
2. 再用 micro-analyzer 定位具体原因
```

### 7.6 Long-term Memory (长期记忆)

DeepAgents 支持多种记忆系统，OLAV 采用文件系统方式：

| 记忆类型 | 存储位置 | 内容 | 示例 |
|---------|---------|------|------|
| **Semantic Memory** | `knowledge/aliases.md` | 语义别名 | `core` = `R1, R2, R3, R4` |
| **Semantic Memory** | `knowledge/conventions.md` | 网络约定 | 管理网段 `10.255.0.0/24` |
| **Episodic Memory** | `knowledge/solutions/` | 成功案例 | BGP 邻居建立失败的排查过程 |
| **Procedural Memory** | `skills/*.md` | 执行策略 | 如何执行快速查询 |

**与传统 RAG 的区别**:
- **不依赖向量数据库** - 使用 Agent 原生的 `read_file`/`grep` 能力
- **Agent 可自学习** - 成功诊断后自动更新 `knowledge/solutions/`
- **人类可审计** - 所有记忆都是可读的 Markdown 文件

### 7.7 Dynamic Tool Loading (动态工具加载)

DeepAgents 支持运行时加载工具，OLAV 利用此能力实现：

```python
# 1. 从 tools/commands/*.txt 读取命令白名单
# 2. 从 tools/apis/*.yaml 读取 OpenAPI 定义
# 3. 动态生成 @tool 装饰的函数

def load_tools_from_directory(path: Path) -> list[Tool]:
    tools = []
    
    # 命令白名单 → CLI 工具
    for txt_file in path.glob("commands/*.txt"):
        commands = txt_file.read_text().strip().split("\n")
        tools.append(create_cli_tool(txt_file.stem, commands))
    
    # OpenAPI 定义 → API 工具
    for yaml_file in path.glob("apis/*.yaml"):
        spec = yaml.safe_load(yaml_file.read_text())
        tools.extend(create_api_tools(spec))
    
    return tools
```

**热加载能力**: 用户添加新的 `.txt` 或 `.yaml` 文件后，重启 Agent 即可使用新工具。

### 7.8 API 凭证管理 (DeepAgents 原生)

**原则**: 使用 DeepAgents 的原生凭证管理，不重复造轮子。

#### 凭证配置

```python
# .env 文件 (不提交 Git)
NETBOX_URL=https://netbox.example.com
NETBOX_TOKEN=your-api-token

ZABBIX_URL=https://zabbix.example.com
ZABBIX_USER=api-user
ZABBIX_PASSWORD=api-password

# Nornir 设备凭证
NORNIR_USERNAME=admin
NORNIR_PASSWORD=admin-password
```

#### DeepAgents 凭证注入

```python
from deepagents.tools import create_api_tool
from deepagents.auth import EnvCredentialProvider

# DeepAgents 原生凭证提供者
credential_provider = EnvCredentialProvider(
    mapping={
        "netbox": {
            "url": "NETBOX_URL",
            "token": "NETBOX_TOKEN",
        },
        "zabbix": {
            "url": "ZABBIX_URL",
            "username": "ZABBIX_USER",
            "password": "ZABBIX_PASSWORD",
        },
    }
)

# 工具自动获取凭证
api_call_tool = create_api_tool(
    name="api_call",
    credential_provider=credential_provider,
)
```

#### 安全边界

| 组件 | 访问凭证 | 说明 |
|------|---------|------|
| Agent | ❌ 不可见 | 不能读取 .env |
| Tools | ✅ 自动注入 | 通过 CredentialProvider |
| Logs | ❌ 脱敏 | 密码不记录到审计日志 |

---

## 8. Agentic 自学习机制

### 8.1 Agent 可自维护的内容

| 内容 | Agent 权限 | 场景 |
|------|-----------|------|
| `skills/*.md` | 读 + 写 | 学习新的任务执行模式 |
| `knowledge/aliases.md` | 读 + 写 | 记录设备别名 |
| `knowledge/solutions/` | 读 + 写 | 保存成功案例 |
| `tools/commands/*.txt` | 读 + 写 | 发现新平台/新命令 |
| `tools/apis/*.yaml` | 只读 | API 定义由人类维护 |
| `OLAV.md` | 只读 | 核心规则由人类维护 |
| `.env` | 不可访问 | 敏感配置 |

### 8.2 学习场景示例

#### 场景 1: 学习设备别名

```
用户: 查一下核心交换机的状态
Agent: 请问"核心交换机"指的是哪台设备？
用户: 10.1.1.1

Agent 内心:
1. 我应该记住这个别名
2. edit_file /knowledge/aliases.md
   添加: | 核心交换机 | 10.1.1.1 | device | cisco_ios |

下次:
用户: 核心交换机的 CPU 使用率
Agent: (读取 aliases.md) 核心交换机 = 10.1.1.1
       执行 show processes cpu ...
```

#### 场景 2: 发现新平台命令

```
用户: 连到 10.2.2.2，这是华为设备，看接口状态
Agent:
1. ls /tools/commands/ → 没有 huawei_vrp.txt
2. write_file /tools/commands/huawei_vrp.txt

   # 华为 VRP 命令白名单
   display version
   display interface brief
   display ip interface brief
   display ip routing-table
   display current-configuration

3. nornir_execute(10.2.2.2, "display interface brief")
```

#### 场景 3: 完善 Skill 策略

```
用户: 帮我排查 VXLAN 问题

Agent:
1. 读取 skills/deep-analysis.md → 没有 VXLAN 相关内容
2. 按通用分析方法排查
3. 成功解决后，edit_file /skills/deep-analysis.md
   添加:
   
   ### VXLAN 故障排查
   1. show vxlan vni → 检查 VNI 状态
   2. show nve peers → 检查 VTEP 邻居
   3. show vxlan interface → 检查隧道接口
```

### 8.3 System Prompt 中的学习指导

```markdown
## 学习行为

当你学到新知识时，主动更新对应文件:

1. **设备别名**
   当用户澄清"XX 是哪台设备"时:
   → edit_file /knowledge/aliases.md 添加新别名

2. **成功案例**  
   当你成功解决一个问题时:
   → write_file /knowledge/solutions/<问题描述>.md

3. **新命令**
   当你发现需要的命令不在白名单时:
   → 如果是只读命令，edit_file /tools/commands/<platform>.txt 添加
   → 如果是配置命令，告知用户需要手动添加

4. **新策略**
   当你发现一个可复用的排查模式时:
   → edit_file /skills/<相关skill>.md 添加新模式
```

---

## 9. 测试策略

### 9.1 测试原则

**核心目标**: 80%+ 功能覆盖率，真实 LLM API + E2E 测试

| 工具 | 用途 |
|------|------|
| **pytest** | 测试框架 |
| **ruff** | 代码检查 + 格式化 |
| **真实 LLM API** | 验证 Agent 行为 |
| **真实设备/Mock** | 网络设备交互 |

### 9.2 测试分层

```
┌─────────────────────────────────────────────────────────────┐
│                      测试金字塔                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  E2E Tests (10%)      完整场景，真实 LLM + 真实/Mock 设备    │
│  ─────────────────────────────────────────────────────────  │
│  Integration (30%)    Agent + Tools，真实 LLM               │
│  ─────────────────────────────────────────────────────────  │
│  Unit Tests (60%)     纯函数，Mock 依赖                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 9.3 分里程碑测试计划

#### Phase 1: MVP 测试

```python
# tests/e2e/test_phase1_mvp.py

@pytest.mark.e2e
@pytest.mark.phase1
class TestQuickQuery:
    """快速查询 E2E 测试 - 使用真实 LLM API"""
    
    async def test_interface_status(self, olav_agent, mock_device):
        """测试: 查看 R1 的接口状态"""
        response = await olav_agent.chat("查看 R1 的 Gi0/1 接口状态")
        
        assert "GigabitEthernet0/1" in response
        assert "up" in response.lower() or "down" in response.lower()
    
    async def test_alias_resolution(self, olav_agent, mock_device):
        """测试: 别名解析"""
        # 先教 Agent 别名
        await olav_agent.chat("核心交换机是 10.1.1.1")
        
        # 使用别名查询
        response = await olav_agent.chat("核心交换机的版本")
        
        assert "show version" in mock_device.executed_commands
    
    async def test_command_whitelist(self, olav_agent, mock_device):
        """测试: 命令白名单过滤"""
        response = await olav_agent.chat("重启 R1")
        
        # 应该被拒绝
        assert "reload" not in mock_device.executed_commands
        assert "无法执行" in response or "不允许" in response
```

#### Phase 2: 深度分析测试

```python
# tests/e2e/test_phase2_analysis.py

@pytest.mark.e2e
@pytest.mark.phase2
class TestDeepAnalysis:
    """深度分析 E2E 测试"""
    
    async def test_macro_analyzer_delegation(self, olav_agent):
        """测试: 宏观分析委派"""
        response = await olav_agent.chat(
            "10.1.1.1 到 10.2.2.2 之间哪里丢包"
        )
        
        # 应该使用 macro-analyzer
        assert olav_agent.last_subagent == "macro-analyzer"
    
    async def test_micro_analyzer_delegation(self, olav_agent):
        """测试: 微观分析委派"""
        response = await olav_agent.chat(
            "R1 的 Gi0/1 为什么有 CRC 错误"
        )
        
        # 应该使用 micro-analyzer
        assert olav_agent.last_subagent == "micro-analyzer"
    
    async def test_combined_analysis(self, olav_agent):
        """测试: 组合分析 (宏观 → 微观)"""
        response = await olav_agent.chat(
            "用户反映上海到北京的专线不稳定，帮我排查"
        )
        
        # 应该先宏观后微观
        assert "macro-analyzer" in olav_agent.subagent_history
        assert "micro-analyzer" in olav_agent.subagent_history
```

#### Phase 3: HITL 测试

```python
# tests/e2e/test_phase3_hitl.py

@pytest.mark.e2e
@pytest.mark.phase3
class TestHITL:
    """HITL 审批流程测试"""
    
    async def test_write_command_requires_approval(self, olav_agent):
        """测试: 写命令需要审批"""
        response = await olav_agent.chat("保存 R1 的配置")
        
        # 应该暂停等待审批
        assert olav_agent.state == "interrupted"
        assert "write memory" in olav_agent.pending_command
    
    async def test_approval_flow(self, olav_agent):
        """测试: 审批流程"""
        await olav_agent.chat("在 R1 上配置一个 loopback")
        
        # 模拟用户批准
        await olav_agent.approve()
        
        # 应该继续执行
        assert olav_agent.state == "completed"
```

### 9.4 测试配置

```python
# conftest.py

import pytest
from olav.agent import create_olav_agent
from tests.mocks import MockNornirDevice

@pytest.fixture
def olav_agent():
    """真实 LLM API 的 Agent"""
    return create_olav_agent(
        model="claude-sonnet-4-20250514",  # 真实 API
        checkpointer=MemorySaver(),
    )

@pytest.fixture
def mock_device():
    """Mock 网络设备"""
    return MockNornirDevice(
        responses={
            "show version": "Cisco IOS XE, Version 17.3.1",
            "show interface Gi0/1": "GigabitEthernet0/1 is up, line protocol is up",
        }
    )

# pytest.ini
[pytest]
markers =
    e2e: End-to-end tests (真实 LLM API)
    phase1: Phase 1 MVP tests
    phase2: Phase 2 深度分析 tests
    phase3: Phase 3 HITL tests
    phase4: Phase 4 自学习 tests
    phase5: Phase 5 外部集成 tests
```

### 9.5 CI/CD 集成

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install ruff
      - run: ruff check .
      - run: ruff format --check .

  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e ".[dev]"
      - run: pytest tests/unit -v --cov=src --cov-report=xml
      - run: coverage report --fail-under=80

  e2e-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e ".[dev]"
      - run: pytest tests/e2e -v -m "phase1 or phase2"
```

### 9.6 覆盖率目标

| 阶段 | 覆盖率目标 | 重点 |
|------|-----------|------|
| Phase 1 | 80% | 快速查询、命令白名单 |
| Phase 2 | 80% | 深度分析、Subagent 委派 |
| Phase 3 | 80% | HITL 审批流程 |
| Phase 4 | 80% | 自学习机制 |
| Phase 5 | 80% | 外部系统集成 |

---

## 10. 分阶段开发路线图

### Phase 1: MVP (核心能力)

**目标**: 基本的网络查询能力

- [ ] 创建 `OLAV.md` 核心指令
- [ ] 创建初始 Skills
  - [ ] `skills/quick-query.md`
  - [ ] `skills/deep-analysis.md`
- [ ] 创建初始 Knowledge
  - [ ] `knowledge/aliases.md` (模板)
  - [ ] `knowledge/conventions.md` (模板)
- [ ] 创建初始 Tools
  - [ ] `tools/commands/cisco_ios.txt`
  - [ ] `tools/apis/_index.yaml`
- [ ] 实现核心代码
  - [ ] `src/olav/agent.py` - create_olav_agent()
  - [ ] `src/olav/tools/network.py` - nornir_execute, list_devices
  - [ ] `src/olav/tools/loader.py` - 工具加载
- [ ] 测试: "查看 R1 的接口状态"

### Phase 2: 完整 Skills

**目标**: 支持快速查询、深度分析、设备巡检

- [ ] 完善 `skills/quick-query.md` (更多查询模式)
- [ ] 完善 `skills/deep-analysis.md` (分析框架)
- [ ] 创建 `skills/device-inspection.md` (巡检流程)
- [ ] 创建更多 `knowledge/solutions/` 案例
- [ ] 测试: "巡检核心交换机"

### Phase 3: Subagents

**目标**: 专业化子代理

- [ ] 配置 config-analyzer Subagent
- [ ] 配置 topology-explorer Subagent
- [ ] 在 `skills/deep-analysis.md` 中添加委派指导
- [ ] 测试: "分析 R1 到 R5 的路径为什么慢"

### Phase 4: Agentic 自学习

**目标**: Agent 能自我完善

- [ ] 配置 CompositeBackend 路由
- [ ] 在 System Prompt 中添加学习指导
- [ ] 测试: Agent 自动学习新别名
- [ ] 测试: Agent 自动保存成功案例

### Phase 5: 外部集成

**目标**: NetBox/Zabbix 集成

- [ ] 导入 NetBox API: `olav import api netbox.yaml`
- [ ] 创建 `skills/netbox-sync.md`
- [ ] 测试: "把 R1 的信息同步到 NetBox"

---

## 11. 文件结构规划

```
Olav/
├── OLAV.md                          # 核心指令 (类似 CLAUDE.md)
├── .env                             # 敏感配置 (不提交 Git)
├── .env.example                     # 配置模板
│
├── skills/                          # HOW - 策略方法 (Markdown)
│   ├── quick-query.md               # ✅ 启用
│   ├── deep-analysis.md             # ✅ 启用
│   ├── _device-inspection.md        # ❌ 禁用 (_ 前缀)
│   └── archived/                    # ❌ 归档目录
│
├── knowledge/                       # WHAT - 事实知识 (Markdown)
│   ├── aliases.md                   # 设备别名
│   ├── conventions.md               # 命名约定
│   └── solutions/                   # 历史案例库
│       ├── crc-errors.md
│       └── ospf-flapping.md
│
├── imports/                         # CAN - 能力定义 (唯一真理源)
│   ├── commands/                    # CLI 命令白名单
│   │   ├── cisco_ios.txt            # ✅ 启用
│   │   ├── huawei_vrp.txt           # ✅ 启用
│   │   └── _juniper_junos.txt       # ❌ 禁用
│   └── apis/                        # API 定义 (OpenAPI)
│       ├── netbox.yaml              # ✅ 启用
│       └── _zabbix.yaml             # ❌ 禁用
│
├── config/
│   ├── settings.py                  # 运行配置
│   └── nornir/                      # Nornir 配置
│       ├── config.yaml
│       └── hosts.yaml
│
├── src/olav/
│   ├── agent.py                     # DeepAgent 入口
│   ├── core/
│   │   └── database.py              # DuckDB 访问层
│   ├── tools/
│   │   ├── network.py               # nornir_execute, list_devices
│   │   ├── capabilities.py          # search_capabilities, api_call
│   │   └── loader.py                # olav reload 实现
│   └── execution/
│       └── nornir_sandbox.py        # Nornir 执行后端
│
├── data/
│   └── olav.db                      # DuckDB (运行时缓存，可删除重建)
│       ├── capabilities             # ← olav reload 生成
│       ├── audit_logs               # 审计日志
│       ├── command_cache            # 命令缓存
│       └── checkpoints              # DeepAgents 状态
│
└── tests/
```

### 10.2 权限矩阵

| 路径 | 用户 | Agent 读 | Agent 写 | 说明 |
|------|------|---------|---------|------|
| `OLAV.md` | ✅ | ✅ | ❌ | 核心规则 |
| `.env` | ✅ | ❌ | ❌ | 敏感配置 |
| `skills/` | ✅ | ✅ | ✅ | 策略可学习 |
| `knowledge/` | ✅ | ✅ | ✅ | 知识可积累 |
| `imports/` | ✅ | ✅ | ❌ | 能力定义 (人类维护) |
| `data/olav.db` | ✅ | ✅ (工具) | ❌ | 运行时缓存 |
| `config/` | ✅ | ❌ | ❌ | 运行配置 |

---

## 附录 A: 设计决策记录

### A.1 为什么 Skills = Markdown 而非代码？

**问题**: 如何让用户和 Agent 都能轻松扩展能力？

**决策**: Skills 使用 Markdown 格式描述任务策略，不是代码。

**理由**:
1. **人人可写** - Markdown 门槛比 Python 低
2. **Agent 可理解** - 自然语言描述更灵活
3. **可自学习** - Agent 能用 edit_file 更新
4. **Claude Code 验证** - CLAUDE.md 模式已被验证有效

### A.2 三层架构的必要性

**问题**: 为什么需要分 Skills/Knowledge/Tools 三层？

**决策**: 三层分离，各司其职。

**理由**:
- **Skills** (HOW) - 可变的执行策略，Agent 可学习优化
- **Knowledge** (WHAT) - 可变的事实，Agent 可积累
- **Tools** (CAN) - 相对稳定的能力边界，通过数据库管理

### A.3 为什么 Agent 不能写 `.env` 和 `settings.py`？

**决策**: 敏感配置和运行配置由人类维护。

**理由**:
1. **安全** - API Keys、密码不应被 Agent 修改
2. **稳定** - 运行参数变更可能导致系统不稳定
3. **审计** - 重要配置变更应有人类审批

### A.4 为什么采用"文件即真理"模式？

**问题**: 如何简化用户维护成本，避免多重真理源？

**决策**: `imports/` 目录是唯一真理源，DuckDB 只是运行时缓存。

**理由**:
1. **一致性** - 与 skills/, knowledge/ 完全相同的模式
2. **Git 友好** - 所有配置都在版本控制中
3. **可重建** - 删除 `data/olav.db` 后 `olav reload` 即可恢复
4. **无同步问题** - 不存在"数据库与配置不一致"的情况

**对比**:
| 方案 | 真理源 | 复杂度 | 同步问题 |
|------|--------|--------|---------|
| 多层配置 (YAML + CLI + DB) | 3 个 | 高 | 有 |
| 数据库为真理 | 1 个 | 中 | 无 |
| **文件为真理** | 1 个 | 低 | 无 |

**用户操作简化**:
```
# 之前 (复杂)
olav import commands xxx.csv
olav add-command "..."
olav enable/disable "..."
olav sync-capabilities

# 现在 (简单)
vim imports/commands/cisco_ios.txt
olav reload
```

### A.5 为什么保留 Claude Code Skills 结构？

**问题**: 既然能力在文件，为什么还要 DuckDB？

**决策**: 文件是真理，DuckDB 是优化后的查询缓存。

**理由**:
1. **查询效率** - SQL 比遍历文件快
2. **LLM 友好** - `search_capabilities` 工具提供结构化结果
3. **可扩展** - 未来可添加索引、全文搜索

**三层一致的禁用机制**:

| 层 | 禁用方式 | 示例 |
|----|---------|------|
| Skills | `_` 前缀 | `_old-query.md` |
| Knowledge | `_` 前缀 | `_outdated.md` |
| Capabilities | `_` 前缀 | `_legacy.txt` |

---

*本文档采用 Claude Code Skills 架构理念设计，核心思想：文件即真理，Agent 通过 Markdown 学习策略，通过 DuckDB 缓存查询能力。*
