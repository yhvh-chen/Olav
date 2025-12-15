# OLAV 多客户端连接与认证机制设计

> 评估日期: 2025-12-07  
> 版本: v0.4.0-beta

---

## 〇、CLI Inspection 执行功能分析

### 0.1 当前状态

**CLI 侧 (`commands.py`)**:
- `olav inspect list` - 列出巡检配置 ✅
- `olav inspect run <profile>` - 触发执行（同步等待）

**Server 侧 (`app.py`)**:
- `POST /inspections/{id}/run` - 触发执行（当前是占位符）
- `InspectionScheduler` - 后台定时执行

### 0.2 是否应该去掉 CLI 执行功能？

| 保留 CLI run 命令 | 去掉 CLI run 命令 |
|------------------|------------------|
| **优点** | **优点** |
| 运维习惯：CLI 直接触发 | 架构清晰：CLI 只读，Server 执行 |
| 调试方便：本地测试 | 避免重复实现 |
| | 权限统一在服务端控制 |
| **缺点** | **缺点** |
| 需要客户端等待执行完成 | 需要轮询/WebSocket 获取进度 |
| 多客户端可能触发冲突 | 用户习惯改变 |

### 0.3 建议方案：保留触发能力，改为异步模式

```
当前模式（同步）:
  olav inspect run profile → 等待执行 → 显示结果
                     ↓
                 客户端阻塞

建议模式（异步触发 + 轮询）:
  olav inspect run profile → 返回 job_id
  olav inspect status job_id → 查询进度
  olav inspect result job_id → 获取结果
                     ↓
                 客户端不阻塞，可以随时查询
```

### 0.4 结论

**不建议完全去掉 CLI 执行功能**，但应该：

1. **改为异步模式** - CLI 触发后立即返回 job_id
2. **执行仍在服务端** - CLI 只是触发 API
3. **增加状态查询** - `olav inspect status <job_id>`
4. **增加报告查看** - `olav report list/show`

---

## 一、当前认证机制评估

### 1.1 现有设计

**位置**: `src/olav/server/auth.py`

```
服务器启动时：
  → 自动生成 secrets.token_urlsafe(32) (或读取 OLAV_API_TOKEN 环境变量)
  → 打印到控制台供用户复制
  → 24 小时有效期 (token_max_age_hours)
  → 所有认证用户视为 admin 角色
```

### 1.2 优点

| 优点 | 说明 |
|------|------|
| **简单易用** | 无需用户名密码注册流程 |
| **零配置** | 启动即可使用 |
| **Multi-worker 兼容** | 支持 `OLAV_API_TOKEN` 环境变量统一 token |

### 1.3 局限性

| 问题 | 影响 |
|------|------|
| **单 Token 共享** | 所有客户端使用同一 token，无法区分用户 |
| **无审计追踪** | 无法知道是哪个客户端/用户执行了操作 |
| **Token 泄露风险高** | 任何获取 token 的人可完全访问 |
| **无撤销机制** | 泄露后只能重启服务器生成新 token |
| **并发状态隔离** | 多客户端可能共享 thread_id 导致状态冲突 |

---

## 二、多客户端支持现状

### 2.1 技术支持情况

**分析位置**: `src/olav/cli/thin_client.py`

```python
class OlavThinClient:
    def __init__(self, config: ClientConfig, auth_token: str | None = None):
        # 每个客户端实例独立
        self._client = httpx.AsyncClient(...)
        self._auth_token = auth_token
```

### 2.2 支持矩阵

| 维度 | 支持情况 | 说明 |
|------|---------|------|
| **并发连接** | ✅ 支持 | FastAPI 原生支持并发 |
| **SSE 流式** | ✅ 支持 | `/orchestrator/stream` 多连接独立 |
| **状态隔离** | ⚠️ 部分 | `thread_id` 需客户端传入，默认可能冲突 |
| **用户区分** | ❌ 不支持 | 所有用户都是 "admin" |
| **会话持久化** | ✅ 支持 | PostgreSQL Checkpointer 按 thread_id 存储 |

### 2.3 问题分析

如果两个客户端使用相同的查询，可能产生相同的 `thread_id`（基于时间戳），导致状态冲突。

---

## 三、认证机制改进建议

### 3.1 方案 A：挑战-Token 模式（推荐短期实施）

```
流程:
1. 客户端请求 POST /auth/challenge 
   → 服务端返回 { challenge_id, challenge_text, expires_in }

2. 管理员在服务端控制台看到 challenge_text 
   → 告知客户端用户

3. 客户端提交 POST /auth/verify
   → { challenge_id, user_input }
   → 验证成功返回 { session_token, expires_at, client_id }

4. session_token 绑定到该客户端，1-24小时有效
```

**优点：**
- 每个客户端有独立 token
- 可追踪每个请求来源
- 泄露影响范围缩小（单客户端）

**实现成本：** 低（在现有架构上扩展）

### 3.2 方案 B：完整身份认证（企业级）

```
用户名 + 密码 → JWT Token (含 user_id, role, permissions)
                     ↓
            PostgreSQL users 表存储
                     ↓
            RBAC 权限控制 (admin/operator/viewer)
```

**适用场景：**
- 多团队使用
- 需要审计合规
- 生产环境长期部署

### 3.3 方案 C：OAuth2/LDAP 集成（企业环境）

```
LDAP/AD → OAuth2 Provider → OLAV API
                ↓
        Single Sign-On (SSO)
```

---

## 四、客户端与服务端配置分离

### 4.1 当前配置架构

```
客户端侧：
  ~/.olav/config.toml          # 服务器 URL、超时
  ~/.olav/credentials          # Token 存储
  OLAV_SERVER_URL 环境变量

服务端侧：
  .env                         # 所有配置（LLM、数据库、认证等）
  config/settings.py           # 默认值和结构化配置
  src/olav/core/settings.py    # Pydantic Settings 加载
```

### 4.2 问题分析

| 问题 | 严重程度 | 说明 |
|------|---------|------|
| **配置耦合** | ⚠️ 中 | `config/settings.py` 同时含 LLM 和路径配置 |
| **客户端配置稀疏** | ⚠️ 中 | 只有 URL/timeout，缺少其他选项 |
| **环境变量冲突** | ⚠️ 低 | 客户端可能误读服务端的环境变量 |

### 4.3 建议配置分离方案

```
服务端配置（.env + config/）：
  ├── .env                     # 敏感凭据（API Key、密码）
  ├── config/server.yaml       # 服务端运行时配置
  │     ├── llm.*
  │     ├── auth.*
  │     ├── features.*
  │     └── infrastructure.*
  └── config/prompts/          # Prompt 模板

客户端配置（~/.olav/）：
  ├── config.toml              # 连接配置
  │     ├── server_url
  │     ├── timeout
  │     ├── default_mode       # standard/expert
  │     └── output_format      # json/table/markdown
  └── credentials              # Token 存储
```

---

## 五、报告拉取机制

### 5.1 当前 API 端点

**位置**: `src/olav/server/app.py`

```python
GET /reports                  # 列出所有报告（分页）
GET /reports/{report_id}      # 获取报告详情（JSON 含 content 字段）
```

### 5.2 CLI 侧实现

**位置**: `src/olav/cli/thin_client.py`

```python
async def get_inspection_report(self, report_id: str) -> dict:
    response = await self._client.get(f"/inspection/reports/{report_id}")
```

### 5.3 功能支持矩阵

| 功能 | API 支持 | CLI 支持 | 说明 |
|------|---------|---------|------|
| **列出报告** | ✅ | ❌ | CLI 未暴露命令 |
| **查看报告** | ✅ | ❌ | CLI 未暴露命令 |
| **下载文件** | ❌ | ❌ | 只返回 JSON，无 raw file 下载 |
| **导出 PDF/HTML** | ❌ | ❌ | 只有 Markdown 格式 |

### 5.4 缺失的 CLI 命令

```bash
olav inspect list             # ✅ 已有 - 列出巡检配置
olav inspect run <profile>    # ✅ 已有 - 运行巡检
olav report list              # ❌ 缺失 - 列出报告
olav report show <id>         # ❌ 缺失 - 查看报告
olav report download <id>     # ❌ 缺失 - 下载报告
```

### 5.5 报告存储位置

```
data/inspection-reports/
  └── inspection_bgp_peer_audit_20251127_231051.md
```

---

## 六、Dashboard 故障排查行为分析

### 6.1 当前 Dashboard 行为

**位置**: `src/olav/cli/display.py`

Dashboard 在故障排查时采用 **流式输出（Streaming）** 模式：

```python
# display.py 第 929-970 行
async for event in self.client.chat_stream(user_input, thread_id=thread_id, mode=self.mode):
    if event_type == StreamEventType.TOOL_START:
        self.console.print(f"[magenta]🔧 Calling {tool_name}...[/magenta]")
    elif event_type == StreamEventType.TOOL_END:
        icon = "✅" if success else "❌"
        self.console.print(f"[magenta]{icon} {tool_name} completed[/magenta]")
    elif event_type == StreamEventType.TOKEN:
        full_response += token
        self.console.print(token, end="")  # 实时打印 token
    elif event_type == StreamEventType.THINKING:
        self.console.print(f"[dim yellow]💭 {thought[:80]}...[/dim yellow]")
```

### 6.2 流式输出过程

```
用户输入查询
    ↓
💭 Thinking... (显示思考过程)
    ↓
🔧 Calling suzieq_query... (工具调用开始)
    ↓
✅ suzieq_query completed (工具完成)
    ↓
Token by token 输出最终回答
    ↓
完成后添加到 chat_history
```

### 6.3 当前问题

| 问题 | 严重程度 | 说明 |
|------|---------|------|
| **无状态查询** | ⚠️ 高 | CLI 无法查询当前工作流的图状态 |
| **无断点续传** | ⚠️ 中 | 网络中断后无法恢复进度 |
| **无历史会话** | ⚠️ 中 | 每次查询生成新的 thread_id，无法延续上下文 |

---

## 七、CLI 状态查询功能建议

### 7.1 建议新增命令

```bash
# 查询当前图状态
olav status                   # 显示当前会话状态
olav status --session <id>    # 查询指定会话状态

# 查询历史会话
olav session list             # 列出最近会话
olav session resume <id>      # 恢复指定会话

# 查询工作流状态
olav workflow status          # 当前工作流状态
olav workflow history         # 工作流执行历史
```

### 7.2 API 端点建议

```python
# 新增端点
GET /sessions                 # 列出用户会话
GET /sessions/{thread_id}     # 获取会话状态
GET /sessions/{thread_id}/state  # 获取 LangGraph 状态

# 响应示例
{
    "thread_id": "abc123",
    "workflow_type": "query_diagnostic",
    "status": "completed",  # running, completed, interrupted, failed
    "current_node": "agent",
    "iteration_count": 3,
    "messages_count": 6,
    "created_at": "2025-12-07T10:00:00Z",
    "updated_at": "2025-12-07T10:05:00Z"
}
```

### 7.3 实现思路

利用现有 PostgreSQL Checkpointer 查询状态：

```python
# 从 checkpointer 获取状态
async def get_session_state(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    state = await checkpointer.aget(config)
    return {
        "thread_id": thread_id,
        "status": "completed" if state else "not_found",
        "messages": len(state.get("messages", [])) if state else 0,
        # ...
    }
```

---

## 八、Inspection 配置与定时位置分析

### 8.1 当前设计

**配置位置**:
- 巡检配置: `config/inspections/*.yaml` (服务端)
- 定时调度: `config/settings.py` → `InspectionConfig` (服务端)
- 调度器: `src/olav/modes/inspection/scheduler.py` (服务端后台进程)

**当前架构**:
```
Server 启动
    ↓
InspectionScheduler.start() 后台任务
    ↓
读取 config/inspections/*.yaml 中的 schedule 字段
    ↓
按 cron 表达式执行巡检
    ↓
生成报告到 data/inspection-reports/
```

### 8.2 问题分析

| 问题 | 当前设计 | 影响 |
|------|---------|------|
| **配置位置** | 服务端 | 客户端无法管理自己的巡检任务 |
| **定时位置** | 服务端后台 | 多用户无法有独立的定时任务 |
| **权限控制** | 无 | 任何客户端都能触发所有巡检 |
| **资源隔离** | 无 | 多用户定时任务可能冲突 |

### 8.3 多用户场景分析

**场景 1: 单租户/团队（当前）**
```
所有用户共享巡检配置
服务端统一调度
✅ 当前设计适用
```

**场景 2: 多租户/多团队**
```
每个团队有独立巡检需求
不同团队管理不同设备
❌ 当前设计不适用
```

### 8.4 建议：保持配置和定时在服务端

**理由**:

| 考虑因素 | 放客户端 | 放服务端（推荐） |
|---------|---------|-----------------|
| **可靠性** | 客户端可能离线 | 服务端 24/7 运行 |
| **一致性** | 多客户端配置可能冲突 | 统一配置源 |
| **资源控制** | 无法限制并发 | 服务端可控制并发 |
| **审计** | 难以追踪 | 统一日志 |

### 8.5 多用户改进建议

**保持服务端调度，增加租户隔离**:

```yaml
# config/inspections/team_a_daily.yaml
name: Team A Daily Check
owner: team_a                    # 新增：所属团队/用户
schedule: "0 9 * * *"
devices:
  filter:
    tenant: team_a               # 按租户过滤设备
checks:
  - name: BGP 状态检查
    tool: suzieq_query
```

**API 级别权限控制**:
```python
@app.post("/inspections/{id}/run")
async def run_inspection(
    id: str,
    current_user: CurrentUser,  # 验证用户权限
):
    inspection = get_inspection(id)
    if inspection.owner != current_user.team:
        raise HTTPException(403, "No permission")
    # ...
```

### 8.6 建议架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         Server Side                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐  │
│  │ config/         │  │ InspectionSched │  │ PostgreSQL     │  │
│  │ inspections/    │→ │ uler (后台)      │→ │ (结果存储)     │  │
│  │ *.yaml          │  │                 │  │                │  │
│  └─────────────────┘  └─────────────────┘  └────────────────┘  │
│         ↑                                          ↓            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    API Layer                             │   │
│  │  POST /inspections (创建/更新配置)                        │   │
│  │  POST /inspections/{id}/run (手动触发)                    │   │
│  │  GET /reports (获取报告)                                  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
          ↑                    ↑                    ↑
     ┌────┴────┐          ┌────┴────┐          ┌────┴────┐
     │ CLI A   │          │ CLI B   │          │ Web GUI │
     │(Team A) │          │(Team B) │          │         │
     └─────────┘          └─────────┘          └─────────┘
```

---

## 九、改进建议优先级

### 优先级 1：认证机制改进（短期实施）

1. **短期**：增加 client_id 参数，每个客户端生成独立 session token ⬅️ **当前实施**
2. **中期**：实现简单的用户名/密码认证 + JWT
3. **长期**：集成 LDAP/OAuth2 企业认证

### 优先级 2：配置分离

1. 创建独立的 `config/server.yaml` 分离服务端配置
2. 扩展 `~/.olav/config.toml` 支持更多客户端选项
3. 考虑支持 `--config` 参数覆盖配置文件

### 优先级 3：报告管理完善

1. 添加 CLI 命令：`olav report list`、`olav report show`、`olav report download`
2. API 增加 `/reports/{id}/download` 端点返回原始文件
3. 考虑增加 PDF/HTML 导出功能

### 优先级 4：多客户端状态隔离

1. `thread_id` 生成规则加入 client_id 前缀
2. 考虑增加 `--session` 参数让用户指定会话名称
3. 清理过期会话状态

### 优先级 5：CLI 状态查询

1. 添加 `olav status` 命令查询当前会话状态
2. 添加 `olav session list/resume` 命令管理会话
3. API 增加 `/sessions` 端点

### 优先级 6：Inspection 异步执行模式

1. `olav inspect run` 改为异步触发，返回 job_id
2. 新增 `olav inspect status <job_id>` 查询进度
3. 新增 `olav inspect result <job_id>` 获取结果
4. 巡检配置增加 `owner` 字段（多用户支持）

---

## 十、短期实施计划：Client Session Token

### 10.1 目标

为每个客户端生成独立的 session token，实现：
- 客户端身份识别
- 请求来源追踪
- 状态隔离（thread_id 前缀）

### 10.2 设计方案

```
认证流程:
┌─────────┐                              ┌─────────────┐
│  CLI    │  1. POST /auth/session       │   Server    │
│ Client  │  ─────────────────────────→  │             │
│         │  { client_name: "cli-abc" }  │             │
│         │                              │             │
│         │  2. 200 OK                   │             │
│         │  ←─────────────────────────  │             │
│         │  { session_token,            │             │
│         │    client_id,                │             │
│         │    expires_at }              │             │
│         │                              │             │
│         │  3. 后续请求带 session_token  │             │
│         │  Authorization: Bearer xxx   │             │
└─────────┘                              └─────────────┘
```

### 10.3 实现 TODO

#### Server 端 (`src/olav/server/auth.py`)

- [ ] **10.3.1** 新增 `SessionToken` 模型
  ```python
  class SessionToken(BaseModel):
      token: str
      client_id: str
      client_name: str
      created_at: datetime
      expires_at: datetime
  ```

- [ ] **10.3.2** 新增会话存储（内存 + Redis 可选）
  ```python
  _active_sessions: dict[str, SessionToken] = {}
  ```

- [ ] **10.3.3** 新增 `POST /auth/session` 端点
  - 接收 client_name（可选）
  - 验证 master token（当前静态 token）
  - 生成 session_token（含 client_id）
  - 返回 session_token + client_id + expires_at

- [ ] **10.3.4** 修改 `validate_token()` 函数
  - 支持验证 session_token
  - 返回 client_id 信息
  - 支持 session 过期检查

- [ ] **10.3.5** 新增 `GET /auth/sessions` 端点（可选）
  - 列出当前活跃会话
  - 管理员功能

- [ ] **10.3.6** 新增 `DELETE /auth/session/{client_id}` 端点
  - 撤销指定会话

#### CLI 端 (`src/olav/cli/`)

- [ ] **10.3.7** `thin_client.py`: 新增 `create_session()` 方法
  ```python
  async def create_session(self, client_name: str | None = None) -> SessionToken:
      response = await self._client.post("/auth/session", json={"client_name": client_name})
      return SessionToken(**response.json())
  ```

- [ ] **10.3.8** `auth.py`: 修改 `CredentialsManager`
  - 存储 session_token 和 client_id
  - 自动刷新过期 session

- [ ] **10.3.9** `commands.py`: 首次连接自动创建 session
  - 检查本地是否有有效 session
  - 没有则调用 `/auth/session` 创建
  - 存储到 `~/.olav/credentials`

- [ ] **10.3.10** `display.py`: thread_id 加入 client_id 前缀
  ```python
  # 当前
  thread_id = str(uuid.uuid4())
  # 改为
  thread_id = f"{client_id}-{uuid.uuid4()}"
  ```

### 10.4 测试计划

- [ ] **10.4.1** 单元测试：session 创建/验证/过期
- [ ] **10.4.2** 集成测试：多客户端并发连接
- [ ] **10.4.3** E2E 测试：CLI 完整流程

### 10.5 向后兼容

- 保留现有 master token 验证逻辑
- master token 可用于创建 session（降级兼容）
- 无 session 时仍使用 master token（旧版 CLI 兼容）

---

## 十、实现路线图

### Phase 1: 基础改进（1-2 周）

- [ ] 实现 `/auth/challenge` 和 `/auth/verify` 端点
- [ ] 添加 `olav report list/show/download` CLI 命令
- [ ] 添加 `olav status` 命令
- [ ] 分离 `config/server.yaml`

### Phase 2: 认证增强（2-4 周）

- [ ] 实现用户名/密码认证
- [ ] PostgreSQL users 表设计
- [ ] JWT token 含 user_id 和 client_id
- [ ] 添加 `/sessions` API 端点

### Phase 3: 多用户支持（4-6 周）

- [ ] Inspection 配置增加 owner 字段
- [ ] API 权限验证
- [ ] 会话状态按用户隔离

### Phase 4: 企业集成（6-10 周）

- [ ] OAuth2 provider 集成
- [ ] LDAP/AD 支持
- [ ] 审计日志记录

---

## 十一、总结

| 评估维度 | 当前状态 | 建议改进 |
|---------|---------|---------|
| **多客户端连接** | ✅ 技术上支持 | 需要状态隔离 |
| **认证安全性** | ⚠️ 单 Token 模式 | 建议实现挑战式认证 |
| **配置分离** | ⚠️ 部分分离 | 建议完全分离 server/client 配置 |
| **报告拉取** | ⚠️ API 有但 CLI 缺 | 补充 CLI 命令 |
| **Dashboard 流式输出** | ✅ SSE 流式 | 增加状态查询功能 |
| **CLI 状态查询** | ❌ 不支持 | 新增 status/session 命令 |
| **Inspection 定时** | ✅ 服务端 | 多用户需增加权限控制 |

### 关键结论

1. **Dashboard 故障排查行为**: 采用 SSE 流式输出，实时显示思考过程和工具调用
2. **CLI 状态查询**: 当前缺失，建议增加 `olav status` 命令利用 Checkpointer 查询图状态
3. **Inspection 配置与定时**: 应保持在服务端，多用户场景增加 owner 字段和权限控制

当前架构适合 **开发和单用户部署**，但如果要支持 **多用户团队使用或生产环境**，认证和状态隔离机制需要加强。

---

## 十二、短期实现已完成（Session Token）

> 实现日期: 2025-12-07

### 12.1 实现内容

#### 服务端 (`src/olav/server/auth.py`)

| 新增内容 | 说明 |
|---------|------|
| `SessionToken` 模型 | token, client_id, client_name, created_at, expires_at |
| `_session_store` | 内存中的 session 存储 (dict[str, SessionToken]) |
| `create_session()` | 创建新 session，默认 7 天有效期 |
| `validate_session()` | 验证 session token，自动清理过期 |
| `get_active_sessions()` | 获取所有活跃 session |
| `revoke_session()` | 撤销指定 session |

#### API 端点 (`src/olav/server/app.py`)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/auth/register` | POST | 客户端注册，返回 session token |
| `/auth/sessions` | GET | 列出所有活跃 session（管理员） |
| `/auth/revoke/{token}` | POST | 撤销指定 session |

#### CLI (`src/olav/cli/commands.py`)

```bash
# 新增命令
olav register --name "my-laptop" --token "master_token_from_server"
olav register -n ci-runner --server http://server:8000
```

**功能**:
- 向服务端注册客户端
- 获取独立的 session token
- 自动保存到 `~/.olav/credentials`

#### Thin Client (`src/olav/cli/thin_client.py`)

新增 `register()` 方法，发送 POST 请求到 `/auth/register`。

#### 凭据管理

Token 查找优先级：
1. `OLAV_API_TOKEN` 环境变量
2. `.env` 文件中的 `OLAV_API_TOKEN`
3. `~/.olav/credentials` 中的 `OLAV_SESSION_TOKEN`

### 12.2 使用流程

```bash
# 1. 服务器启动，打印 master token
docker-compose up olav-server
# 输出: 🔑 ACCESS TOKEN: abc123...

# 2. 客户端注册
olav register --name "alice-laptop" --token "abc123..."
# 输出:
#   ✅ Registration successful!
#   Client ID: 550e8400-e29b-41d4-a716-446655440000
#   Credentials saved to ~/.olav/credentials

# 3. 后续使用（自动使用 session token）
olav query "查询 R1 BGP 状态"
```

### 12.3 认证优先级

`get_current_user()` 验证顺序：
1. 检查 `AUTH_DISABLED` 环境变量
2. 尝试 session token 验证 (`validate_session`)
3. 回退到 master token 验证 (`validate_token`)

### 12.4 后续改进

- [ ] 持久化 session 到 Redis/PostgreSQL
- [ ] 添加 session 刷新机制
- [x] ~~支持 session 列表和管理命令 (`olav session list`)~~ ✅ 已实现
- [x] ~~支持显式 logout (`olav logout`)~~ ✅ 已实现

---

## 十三、中期任务已完成

> 实现日期: 2025-12-07

### 13.1 状态与会话管理

#### `olav status` 命令
```bash
olav status           # 显示服务器和认证状态
olav status --json    # JSON 输出
```

**显示内容**:
- 服务器 URL、状态、版本
- Orchestrator 就绪状态
- 当前认证用户和 client_id

#### `olav session` 子命令
```bash
olav session list     # 列出所有活跃 session（需要 master token）
olav session logout   # 登出并撤销当前 session
```

### 13.2 报告管理

#### `olav report` 子命令
```bash
olav report list                # 列出最近报告
olav report list --limit 10     # 限制数量
olav report show <report_id>    # 显示报告详情
olav report show <id> --raw     # 原始 markdown
olav report download <id>       # 下载到本地
olav report download <id> -o ./my_report.md
```

### 13.3 Inspection 异步模式

#### 新增服务端组件

**`src/olav/server/jobs.py`** - Job 管理模块:
- `Job` 模型: job_id, inspection_id, status, progress, report_id
- `JobStore` 类: 内存存储，支持 create/get/update/list
- `JobStatus` 枚举: pending, running, completed, failed

#### 新增 API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/inspections/{id}/run` | POST | 触发执行，返回 job_id |
| `/inspections/jobs` | GET | 列出所有 job |
| `/inspections/jobs/{job_id}` | GET | 查询单个 job 状态 |

#### CLI 命令更新

```bash
# 异步模式（默认）
olav inspect run bgp_peer_audit
# 输出: ✅ Inspection queued. Job ID: 550e8400...

# 等待模式
olav inspect run bgp_peer_audit --wait

# 查询状态
olav inspect status <job_id>

# 列出所有 job
olav inspect jobs
olav inspect jobs --limit 10
```

### 13.4 完整命令一览

```bash
# 认证
olav register --name "my-laptop" --token <master_token>
olav status
olav session list
olav session logout

# 查询
olav query "检查 R1 BGP 状态"
olav                           # 交互模式

# 巡检（异步）
olav inspect list
olav inspect run <profile>
olav inspect run <profile> --wait
olav inspect status <job_id>
olav inspect jobs

# 报告
olav report list
olav report show <report_id>
olav report download <report_id>

# 文档
olav doc list
olav doc search "BGP 配置"
```

### 13.5 后续改进

- [ ] Job 持久化到 Redis/PostgreSQL
- [ ] 实际执行 inspection（当前只是框架）
- [ ] SSE 推送 job 进度更新
- [ ] Job 取消功能

