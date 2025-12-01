# OLAV WebGUI Architecture Design

## Overview

本文档定义 OLAV WebGUI 的技术架构和实现方案，基于现有后端 API 能力进行前端技术选型。

## Backend API Capabilities

| OLAV 后端能力 | 端点 | WebGUI 需求 |
|---------------|------|-------------|
| SSE 流式响应 | `POST /orchestrator/stream` | 实时渲染 AI 回复 |
| 同步调用 | `POST /orchestrator/invoke` | 简单查询 |
| HITL 中断审批 | LangGraph interrupt | 交互式确认弹窗 |
| Token 认证 | 启动时自动生成 | Token 输入/会话管理 |
| 公共配置 | `GET /config` | 功能开关/限制 |
| 健康检查 | `GET /health` | 服务状态监控 |
| 用户信息 | `GET /me` | Token 验证/用户展示 |

## Technology Stack

### Core Framework

| 技术 | 版本 | 用途 | 选型理由 |
|------|------|------|----------|
| **Next.js** | 14+ (App Router) | 全栈框架 | SSE 原生支持、TypeScript、静态导出 |
| **React** | 18+ | UI 库 | 生态成熟、Server Components |
| **TypeScript** | 5.x | 类型安全 | 与后端 Pydantic 模型对齐 |

### UI Layer

| 技术 | 用途 | 选型理由 |
|------|------|----------|
| **shadcn/ui** | 组件库 | 复制即用、无依赖膨胀、高度可定制 |
| **Tailwind CSS** | 样式 | 原子化 CSS、深色模式原生支持 |
| **Radix UI** | 无障碍基础 | shadcn 底层依赖 |
| **Lucide Icons** | 图标 | 轻量、与 shadcn 集成 |

### State & Data

| 技术 | 用途 | 选型理由 |
|------|------|----------|
| **Zustand** | 全局状态 | 轻量 (<1KB)、无 Provider 嵌套 |
| **React Query (TanStack)** | 服务端状态 | 缓存、重试、乐观更新 |
| **EventSource API** | SSE 处理 | 原生支持、无额外依赖 |

### Visualization

| 技术 | 用途 | 选型理由 |
|------|------|----------|
| **React Flow** | 网络拓扑 | 交互式节点图、缩放/平移 |
| **Recharts** | 指标图表 | React 友好、轻量 |

### Internationalization

| 技术 | 用途 | 选型理由 |
|------|------|----------|
| **next-intl** | i18n | App Router 原生支持、中英文切换 |

### Code Quality

| 技术 | 用途 |
|------|------|
| **ESLint** | 代码检查 |
| **Prettier** | 代码格式化 |
| **Husky** | Git hooks |

---

## Project Structure

```
olav-webgui/
├── app/                          # Next.js App Router
│   ├── (auth)/                   # 认证路由组
│   │   └── login/
│   │       └── page.tsx
│   ├── (dashboard)/              # 主应用路由组
│   │   ├── layout.tsx            # 共享布局（侧边栏）
│   │   ├── chat/
│   │   │   ├── page.tsx          # 新会话
│   │   │   └── [sessionId]/
│   │   │       └── page.tsx      # 历史会话
│   │   ├── topology/
│   │   │   └── page.tsx          # 网络拓扑
│   │   ├── devices/
│   │   │   └── page.tsx          # 设备管理
│   │   ├── history/
│   │   │   └── page.tsx          # 执行历史
│   │   └── settings/
│   │       └── page.tsx          # 用户设置
│   ├── api/                      # BFF 代理层 (可选)
│   │   └── [...proxy]/
│   │       └── route.ts
│   ├── layout.tsx                # 根布局
│   ├── page.tsx                  # 根页面 (重定向)
│   └── globals.css               # 全局样式
│
├── components/
│   ├── ui/                       # shadcn/ui 组件
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── dialog.tsx
│   │   └── ...
│   ├── chat/                     # 聊天相关组件
│   │   ├── message-list.tsx
│   │   ├── message-item.tsx
│   │   ├── chat-input.tsx
│   │   ├── streaming-text.tsx
│   │   └── workflow-selector.tsx
│   ├── hitl/                     # HITL 审批组件
│   │   ├── approval-card.tsx
│   │   ├── execution-plan.tsx
│   │   └── confirmation-dialog.tsx
│   ├── topology/                 # 拓扑组件
│   │   ├── network-graph.tsx
│   │   ├── device-node.tsx
│   │   └── connection-edge.tsx
│   ├── layout/                   # 布局组件
│   │   ├── sidebar.tsx
│   │   ├── header.tsx
│   │   └── theme-toggle.tsx
│   └── common/                   # 通用组件
│       ├── loading.tsx
│       ├── error-boundary.tsx
│       └── markdown-renderer.tsx
│
├── lib/
│   ├── api/                      # API 客户端
│   │   ├── client.ts             # Axios/Fetch 配置
│   │   ├── auth.ts               # 认证 API
│   │   ├── orchestrator.ts       # 工作流 API
│   │   └── types.ts              # API 类型定义
│   ├── sse/                      # SSE 处理
│   │   ├── stream-handler.ts
│   │   └── message-parser.ts
│   ├── stores/                   # Zustand stores
│   │   ├── auth-store.ts
│   │   ├── chat-store.ts
│   │   └── config-store.ts
│   ├── hooks/                    # 自定义 Hooks
│   │   ├── use-auth.ts
│   │   ├── use-stream.ts
│   │   └── use-config.ts
│   └── utils/                    # 工具函数
│       ├── cn.ts                 # className 合并
│       └── format.ts
│
├── messages/                     # i18n 翻译
│   ├── en.json
│   └── zh.json
│
├── public/                       # 静态资源
│   └── logo.svg
│
├── styles/                       # 额外样式
│   └── markdown.css
│
├── .env.example                  # 环境变量模板
├── .env.local                    # 本地环境变量
├── next.config.js
├── tailwind.config.js
├── tsconfig.json
├── package.json
└── README.md
```

---

## Authentication Design

### 单 Token 认证模式

**OLAV 采用简化的单 Token 认证**，服务器启动时自动生成 Token 并打印到控制台。

#### 设计理念

- **简单优先**：无需用户名/密码，无需数据库
- **快速迭代**：减少开发和测试复杂度
- **容器友好**：通过环境变量 `OLAV_API_TOKEN` 支持多副本部署

#### 认证流程

```
┌─────────────────────────────────────────────────────────────┐
│                    Single Token 认证流程                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 后端启动时生成 Token 并打印到控制台:                      │
│     🔑 ACCESS TOKEN: xxxxx-xxxxx-xxxxx                      │
│     🌐 WebGUI URL: http://localhost:3100?token=xxxxx        │
│     ↓                                                       │
│  2. 用户访问 WebGUI:                                         │
│     ├── 方式 A: 点击控制台打印的 URL (自动携带 token)          │
│     ├── 方式 B: 手动访问 /login 页面，粘贴 Token              │
│     └── Token 存储到 localStorage                           │
│     ↓                                                       │
│  3. 验证 Token: GET /me                                     │
│     ├── 成功 → 跳转 /chat                                   │
│     └── 失败 → 显示错误，返回 Token 输入页                   │
│     ↓                                                       │
│  4. 后续请求: Authorization: Bearer <token>                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Token 获取方式

**方式 1: 从服务器日志复制**

```bash
# 启动服务器后，控制台会打印:
============================================================
🔑 ACCESS TOKEN (valid for 24 hours):
   Abc123XyzTokenStringHere...

🌐 WebGUI URL (click to open):
   http://localhost:3100?token=Abc123XyzTokenStringHere...

📖 API Docs: http://localhost:8000/docs
============================================================
```

**方式 2: 环境变量预设** (多副本/Docker 部署)

```bash
# .env 或 docker-compose.yml
OLAV_API_TOKEN=your-predefined-secure-token
```

#### Token 输入页面 UI

```
┌─────────────────────────────────────────┐
│                                         │
│            🔐 OLAV WebGUI               │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │ 粘贴 Access Token...            │    │
│  └─────────────────────────────────┘    │
│                                         │
│         [ 验证并进入 ]                   │
│                                         │
│  ────────────────────────────────────   │
│                                         │
│  💡 Token 获取方式:                      │
│     查看服务器启动日志中的 ACCESS TOKEN  │
│                                         │
│  🔗 或直接使用日志中打印的 WebGUI URL    │
│                                         │
└─────────────────────────────────────────┘
```

#### 认证状态管理

```typescript
// lib/stores/auth-store.ts
interface AuthState {
  token: string | null;
  user: User | null;
  isValidating: boolean;
  
  // Single Token 模式
  setToken: (token: string) => Promise<boolean>;  // 验证并存储
  clearAuth: () => void;
}
```

#### URL Token 自动登录

WebGUI 支持从 URL query 参数读取 Token，实现一键登录：

```typescript
// app/login/page.tsx
useEffect(() => {
  const urlToken = searchParams.get('token');
  if (urlToken) {
    // 自动验证并登录
    validateAndSetToken(urlToken);
  }
}, []);
```

#### 安全考虑

| 场景 | 措施 |
|------|------|
| Token 泄露 | 24 小时自动过期，重启服务器生成新 Token |
| 暴力破解 | 43 字符 URL-safe Base64，熵值足够高 |
| 多副本部署 | 使用 `OLAV_API_TOKEN` 环境变量统一 Token |
| 生产环境 | 建议配合 HTTPS + 反向代理使用 |

---

## Core Pages

### 1. Token Entry (`/login`)

```
┌─────────────────────────────────┐
│           🔐 OLAV               │
│                                 │
│  ┌───────────────────────────┐  │
│  │ 粘贴 Access Token...      │  │
│  └───────────────────────────┘  │
│                                 │
│       [ 验证并进入 ]            │
│                                 │
│  ─────────────────────────────  │
│  💡 Token 获取方式:              │
│  查看服务器启动日志              │
│                                 │
│  Environment: local             │
└─────────────────────────────────┘
```

**功能**:
- Token 粘贴输入
- URL ?token= 自动登录
- `GET /me` 验证
- 错误提示

### 2. Chat (`/chat`)

```
┌──────┬──────────────────────────────────────────┐
│      │  Query Diagnostic ▼  │ + New Session    │
│ S    ├──────────────────────────────────────────┤
│ I    │                                          │
│ D    │  [User]: 查询 R1 的 BGP 邻居状态          │
│ E    │                                          │
│ B    │  [Assistant]: 正在查询...                │
│ A    │  ┌────────────────────────────────────┐  │
│ R    │  │ BGP Neighbors for R1:              │  │
│      │  │ ┌─────────┬────────┬─────────────┐ │  │
│      │  │ │ Peer    │ State  │ Uptime      │ │  │
│      │  │ ├─────────┼────────┼─────────────┤ │  │
│      │  │ │ 10.0.0.2│ Estab  │ 5d 12:34:56 │ │  │
│      │  │ └─────────┴────────┴─────────────┘ │  │
│      │  └────────────────────────────────────┘  │
│      │                                          │
│      ├──────────────────────────────────────────┤
│      │ ┌────────────────────────────────────┐   │
│      │ │ 输入您的问题...                    │   │
│      │ └────────────────────────────────────┘   │
│      │                              [Send] ➤    │
└──────┴──────────────────────────────────────────┘
```

**功能**:
- 工作流选择器 (Query/Execution/NetBox/DeepDive)
- 流式消息渲染 (打字机效果)
- Markdown 渲染 (代码块、表格)
- 会话历史侧边栏

### 3. HITL Approval (嵌入 Chat)

```
┌────────────────────────────────────────────────┐
│ ⚠️  Execution Plan Requires Approval           │
├────────────────────────────────────────────────┤
│                                                │
│  Target Device: R1 (192.168.1.1)               │
│  Operation: Configure BGP Neighbor             │
│                                                │
│  Commands to Execute:                          │
│  ┌──────────────────────────────────────────┐  │
│  │ router bgp 65001                         │  │
│  │   neighbor 10.0.0.2 remote-as 65002      │  │
│  │   neighbor 10.0.0.2 update-source lo0    │  │
│  └──────────────────────────────────────────┘  │
│                                                │
│  Risk Level: 🟡 Medium                         │
│                                                │
│  [ Cancel ]              [ ✓ Approve & Execute ] │
└────────────────────────────────────────────────┘
```

**功能**:
- 执行计划预览
- 风险等级指示
- 确认/拒绝按钮
- 超时自动取消

### 4. Topology (`/topology`)

```
┌──────┬──────────────────────────────────────────┐
│      │  Network Topology          [Refresh]    │
│ S    ├──────────────────────────────────────────┤
│ I    │                                          │
│ D    │         ┌─────┐                          │
│ E    │         │ R1  │                          │
│ B    │         └──┬──┘                          │
│ A    │       ┌────┴────┐                        │
│ R    │    ┌──┴──┐   ┌──┴──┐                     │
│      │    │ SW1 │   │ SW2 │                     │
│      │    └──┬──┘   └──┬──┘                     │
│      │    ┌──┴──┐   ┌──┴──┐                     │
│      │    │ H1  │   │ H2  │                     │
│      │    └─────┘   └─────┘                     │
│      │                                          │
│      ├──────────────────────────────────────────┤
│      │ Selected: R1 │ Status: Up │ Query ➤     │
└──────┴──────────────────────────────────────────┘
```

**功能**:
- React Flow 交互式拓扑
- 点击设备查询详情
- 故障节点高亮
- 缩放/平移

### 5. History (`/history`)

```
┌──────┬──────────────────────────────────────────┐
│      │  Execution History         [Export CSV] │
│ S    ├──────────────────────────────────────────┤
│ I    │  Filter: [All Workflows ▼] [This Week ▼]│
│ D    ├──────────────────────────────────────────┤
│ E    │  ┌────────────────────────────────────┐  │
│ B    │  │ 2025-11-30 10:23 │ Query      │ ✓  │  │
│ A    │  │ 查询 R1 BGP 状态                   │  │
│ R    │  └────────────────────────────────────┘  │
│      │  ┌────────────────────────────────────┐  │
│      │  │ 2025-11-30 09:15 │ Execution  │ ✓  │  │
│      │  │ 配置 OSPF 邻居                     │  │
│      │  └────────────────────────────────────┘  │
│      │  ┌────────────────────────────────────┐  │
│      │  │ 2025-11-29 16:42 │ DeepDive   │ ✗  │  │
│      │  │ 诊断网络延迟问题                   │  │
│      │  └────────────────────────────────────┘  │
└──────┴──────────────────────────────────────────┘
```

**功能**:
- 执行历史列表
- 筛选/搜索
- 详情展开
- 导出 CSV

---

## Key Interaction Patterns

### 1. SSE Streaming Flow

#### Current Backend Support

| 能力 | 状态 | 说明 |
|------|------|------|
| 最终消息 Token 流 | ✅ 已支持 | `stream_mode="values"` |
| 工具调用事件 | ✅ 已支持 | `AIMessage.tool_calls` |
| 思考过程流式 | ⚠️ 需扩展 | 存在但未暴露到 SSE |
| HITL 中断 | ✅ 已支持 | LangGraph interrupt |

#### Extended Stream Event Schema

后端需要扩展 `/orchestrator/stream` 输出格式以支持思考过程：

```typescript
// lib/api/types.ts
interface StreamChunk {
  type: 'token' | 'thinking' | 'tool_start' | 'tool_end' | 'interrupt' | 'error';
  
  // type: 'token' - 最终回复 token
  content?: string;
  
  // type: 'thinking' - LLM 思考过程 (DeepPath/DeepDive)
  thinking?: {
    step: 'hypothesis' | 'verification' | 'conclusion' | 'reasoning';
    content: string;      // 思考内容
    hypothesis?: string;  // 当前假设
    confidence?: number;  // 置信度 0-1
    iteration?: number;   // 推理迭代次数
  };
  
  // type: 'tool_start' - 工具开始调用
  // type: 'tool_end' - 工具调用完成
  tool?: {
    id: string;           // 工具调用 ID
    name: string;         // 工具名称
    display_name: string; // 中文显示名
    args: Record<string, any>;
    result?: any;         // 仅 tool_end
    duration_ms?: number; // 仅 tool_end
    success?: boolean;    // 仅 tool_end
  };
  
  // type: 'interrupt' - HITL 审批
  execution_plan?: ExecutionPlan;
  
  // type: 'error'
  error?: {
    code: string;
    message: string;
  };
}
```

#### Frontend Rendering Example

```tsx
// components/chat/streaming-text.tsx
export function StreamingMessage({ stream }: { stream: AsyncIterable<StreamChunk> }) {
  const [tokens, setTokens] = useState<string>('');
  const [thinking, setThinking] = useState<ThinkingStep[]>([]);
  const [activeTool, setActiveTool] = useState<ToolCall | null>(null);

  useEffect(() => {
    (async () => {
      for await (const chunk of stream) {
        switch (chunk.type) {
          case 'token':
            setTokens(prev => prev + chunk.content);
            break;
            
          case 'thinking':
            setThinking(prev => [...prev, chunk.thinking!]);
            break;
            
          case 'tool_start':
            setActiveTool(chunk.tool!);
            break;
            
          case 'tool_end':
            setActiveTool(null);
            // 可选：显示工具结果
            break;
            
          case 'interrupt':
            // 触发 HITL 审批弹窗
            showApprovalDialog(chunk.execution_plan!);
            break;
        }
      }
    })();
  }, [stream]);

  return (
    <div>
      {/* 思考过程折叠面板 */}
      {thinking.length > 0 && (
        <ThinkingProcess steps={thinking} />
      )}
      
      {/* 当前工具调用指示器 */}
      {activeTool && (
        <ToolIndicator tool={activeTool} />
      )}
      
      {/* 主消息内容 */}
      <MarkdownRenderer content={tokens} />
    </div>
  );
}
```

#### Thinking Process UI Component

```tsx
// components/chat/thinking-process.tsx
export function ThinkingProcess({ steps }: { steps: ThinkingStep[] }) {
  const [expanded, setExpanded] = useState(false);
  
  return (
    <Collapsible open={expanded} onOpenChange={setExpanded}>
      <CollapsibleTrigger className="flex items-center gap-2 text-sm text-muted-foreground">
        <Brain className="h-4 w-4" />
        <span>思考过程 ({steps.length} 步)</span>
        <ChevronDown className={cn("h-4 w-4", expanded && "rotate-180")} />
      </CollapsibleTrigger>
      
      <CollapsibleContent>
        <div className="mt-2 space-y-2 border-l-2 border-muted pl-4">
          {steps.map((step, i) => (
            <div key={i} className="text-sm">
              <Badge variant="outline">{stepLabels[step.step]}</Badge>
              <p className="mt-1 text-muted-foreground">{step.content}</p>
              {step.confidence && (
                <Progress value={step.confidence * 100} className="mt-1 h-1" />
              )}
            </div>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

const stepLabels = {
  hypothesis: '🔍 假设',
  verification: '✅ 验证',
  conclusion: '💡 结论',
  reasoning: '🧠 推理',
};
```

#### Backend Enhancement Required

> **TODO**: 后端需要在 `src/olav/server/app.py` 中扩展流式输出，
> 将 `DeepPathStrategy.reasoning_trace` 和工具调用事件暴露到 SSE。
>
> 参考实现：
> - `src/olav/ui/chat_ui.py` - `create_thinking_context()` 已有 CLI 版本
> - `src/olav/strategies/deep_path.py` - `ReasoningState` 包含完整推理链
> - `src/olav/main.py:632` - 当前 `astream()` 处理逻辑

#### Stream Handler Implementation

```typescript
// lib/sse/stream-handler.ts
export async function* streamOrchestrator(
  messages: Message[],
  token: string
): AsyncGenerator<StreamChunk> {
  const response = await fetch('/orchestrator/stream', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ input: { messages } }),
  });

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');
    
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        yield JSON.parse(line.slice(6));
      }
    }
  }
}
```

### 2. HITL Interrupt Handling

```typescript
// lib/hooks/use-hitl.ts
export function useHITL() {
  const [pendingApproval, setPendingApproval] = useState<ExecutionPlan | null>(null);

  const handleStreamChunk = (chunk: StreamChunk) => {
    if (chunk.type === 'interrupt') {
      setPendingApproval(chunk.execution_plan);
    }
  };

  const approve = async (planId: string) => {
    await api.post(`/orchestrator/resume/${planId}`, { decision: 'approve' });
    setPendingApproval(null);
  };

  const reject = async (planId: string) => {
    await api.post(`/orchestrator/resume/${planId}`, { decision: 'reject' });
    setPendingApproval(null);
  };

  return { pendingApproval, handleStreamChunk, approve, reject };
}
```

### 3. Auth State Management

```typescript
// lib/stores/auth-store.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthState {
  token: string | null;
  user: User | null;
  setToken: (token: string) => Promise<boolean>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setToken: async (token) => {
        // Validate token via GET /me
        const user = await api.getMe(token);
        if (user) {
          set({ token, user });
          return true;
        }
        return false;
      },
      logout: () => set({ token: null, user: null }),
    }),
    { name: 'olav-auth' }
  )
);
```

---

## Environment Variables

```bash
# .env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_APP_NAME=OLAV
NEXT_PUBLIC_DEFAULT_LOCALE=zh
```

---

## Development Phases

### Phase 1: Foundation (Week 1-2)
- [ ] 项目脚手架 (Next.js + shadcn/ui)
- [ ] 登录页面 + JWT 认证
- [ ] 基础聊天界面
- [ ] SSE 流式消息

### Phase 2: HITL Integration (Week 3)
- [ ] 审批卡片组件
- [ ] 中断/恢复流程
- [ ] 执行状态追踪

### Phase 3: Visualization (Week 4)
- [ ] React Flow 拓扑图
- [ ] 设备详情面板
- [ ] 指标图表

### Phase 4: Polish (Week 5)
- [ ] 历史/审计页面
- [ ] i18n 国际化
- [ ] 深色模式
- [ ] 响应式布局

### Phase 5: Production (Week 6)
- [ ] 性能优化
- [ ] 错误处理
- [ ] Docker 集成
- [ ] 文档完善

---

## Alternatives Considered

| 方案 | 排除原因 |
|------|----------|
| Vue/Nuxt | 团队已有 Python + TS 经验，React 生态更成熟 |
| Angular | 过于重量级，学习曲线陡峭 |
| Svelte | 社区较小，企业支持有限 |
| Vite + React | 需自建路由/SSR，Next.js 开箱即用 |
| Ant Design | 风格过于传统"管理后台"，不够现代 |
| MUI | 依赖过重，主题定制复杂 |
| Socket.IO | SSE 已足够，无需双向通信 |

---

## Integration with OLAV Backend

### API Client Configuration

```typescript
// lib/api/client.ts
import axios from 'axios';
import { useAuthStore } from '@/lib/stores/auth-store';

const client = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL,
});

client.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default client;
```

### Type Definitions (Mirror Pydantic Models)

```typescript
// lib/api/types.ts
export interface User {
  username: string;
  role: 'admin' | 'operator' | 'viewer';
  disabled: boolean;
}

export interface PublicConfig {
  version: string;
  environment: 'local' | 'docker';
  features: {
    expert_mode: boolean;
    agentic_rag_enabled: boolean;
    deep_dive_memory_enabled: boolean;
    dynamic_router_enabled: boolean;
  };
  ui: {
    default_language: string;
    streaming_enabled: boolean;
    websocket_heartbeat_seconds: number;
  };
  limits: {
    max_query_length: number;
    session_timeout_minutes: number;
    rate_limit_rpm: number | null;
  };
  workflows: string[];
}

export interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface StreamChunk {
  type: 'token' | 'message' | 'interrupt' | 'error';
  content?: string;
  execution_plan?: ExecutionPlan;
}

export interface ExecutionPlan {
  id: string;
  device: string;
  operation: string;
  commands: string[];
  risk_level: 'low' | 'medium' | 'high';
}
```

---

## References

- [Next.js Documentation](https://nextjs.org/docs)
- [shadcn/ui](https://ui.shadcn.com/)
- [React Flow](https://reactflow.dev/)
- [Zustand](https://zustand-demo.pmnd.rs/)
- [TanStack Query](https://tanstack.com/query)
- [next-intl](https://next-intl-docs.vercel.app/)

---

## Implementation Status

### Phase 1 进度 (当前)

| 组件 | 状态 | 文件 |
|------|------|------|
| 项目脚手架 | ✅ 完成 | `webgui/package.json`, `tsconfig.json` |
| Tailwind + CSS 变量 | ✅ 完成 | `globals.css`, `tailwind.config.js` |
| API 类型定义 | ✅ 完成 | `lib/api/types.ts` |
| SSE 流式客户端 | ✅ 完成 | `lib/api/client.ts` |
| Zustand Auth Store | ✅ 完成 | `lib/stores/auth-store.ts` |
| Zustand Chat Store | ✅ 完成 | `lib/stores/chat-store.ts` |
| Chat 页面 | ✅ 完成 | `app/chat/page.tsx` |
| 思考过程面板 | ✅ 完成 | `ThinkingPanel` in chat/page.tsx |
| 工具调用指示器 | ✅ 完成 | `ToolIndicator` in chat/page.tsx |
| HITL 审批对话框 | ✅ 完成 | `components/hitl-dialog.tsx` |
| Markdown 消息渲染 | ✅ 完成 | `components/message-bubble.tsx` |
| 模式选择器 | ✅ 完成 | `components/mode-selector.tsx` |
| Docker 配置 | ✅ 完成 | `webgui/Dockerfile` |
| **Token 认证页面** | ✅ 完成 | `app/login/page.tsx` |
| **Auth Guard 组件** | ✅ 完成 | `components/auth-guard.tsx` |
| **路由保护中间件** | ✅ 完成 | `middleware.ts` |

### 待实现

| 功能 | 优先级 | 依赖 |
|------|--------|------|
| ~~Token 输入页面~~ | ~~P0~~ | ✅ 已完成 |
| ~~路由保护 (middleware)~~ | ~~P0~~ | ✅ 已完成 |
| ~~后端连接测试~~ | ~~P1~~ | ✅ 已完成 (E2E tests passing) |
| ~~Docker Compose 集成~~ | ~~P1~~ | ✅ 已完成 (olav-webgui service) |
| ~~Single Token Auth 对齐~~ | ~~P1~~ | ✅ 已完成 (removed JWT) |
| ~~会话历史侧边栏~~ | ~~P2~~ | ✅ 已完成 (SessionSidebar + /sessions API) |
| ~~网络拓扑页面~~ | ~~P3~~ | ✅ 已完成 (React Flow + /topology API) |
| ~~执行历史页面~~ | ~~P2~~ | ✅ 已完成 (history-store + /history page) |
| ~~巡检报告阅读~~ | ~~P2~~ | ✅ 已完成 (reports-store + /reports page + detail view) |

---

## Future Features (Backlog)

以下功能暂不在 MVP 范围内，待 Chat + Token 认证验证后考虑：

### 1. RAG 文档管理 (Phase 3+)

**需后端支持**：
- `POST /documents/upload` - 文件上传
- `GET /documents` - 文档列表
- `DELETE /documents/{id}` - 删除文档
- `GET /documents/{id}/status` - 向量化进度

**WebGUI 组件**：
```
┌──────────────────────────────────────────────────┐
│  📚 知识库管理                    [上传文档]     │
├──────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────┐  │
│  │ 📄 Cisco_BGP_Guide.pdf         ✅ 已索引   │  │
│  │    12.5 MB │ 2024-11-28 │ 326 chunks      │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │ 📄 Network_Troubleshooting.docx  🔄 处理中 │  │
│  │    2.3 MB │ 2024-11-30 │ ████░░░░ 45%     │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

### 2. 巡检模式设置 (Phase 3+)

**利用现有配置**：`config/inspections/*.yaml`

**WebGUI 组件**：
```
┌──────────────────────────────────────────────────┐
│  🔍 巡检模式                      [新建规则]     │
├──────────────────────────────────────────────────┤
│  ◉ 快速巡检 (5 分钟)                             │
│    检查：BGP 邻居状态、接口 Up/Down              │
│                                                  │
│  ○ 深度巡检 (30 分钟)                            │
│    检查：路由表一致性、QoS 策略、ACL 合规         │
│                                                  │
│  ○ 自定义巡检                                    │
│    [选择检查项...]                               │
├──────────────────────────────────────────────────┤
│  目标范围：[全部设备 ▼]  [开始巡检]              │
└──────────────────────────────────────────────────┘
```

### 3. 报告阅读 (Phase 2+)

**利用现有数据**：`data/inspection-reports/`

**WebGUI 组件**：
```
┌──────────────────────────────────────────────────┐
│  📊 巡检报告                     [导出 PDF]      │
├──────────────────────────────────────────────────┤
│  执行时间: 2024-11-30 10:23:45                   │
│  模式: 深度巡检 │ 耗时: 28m 34s                   │
│  状态: ✅ 通过 (2 警告)                           │
├──────────────────────────────────────────────────┤
│  📌 问题摘要                                     │
│  ┌────────────────────────────────────────────┐  │
│  │ ⚠️ R3: BGP 邻居 10.0.0.5 Idle (3 小时)     │  │
│  │ ⚠️ SW2: 接口 Gi0/1 CRC 错误 > 阈值         │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  📈 指标趋势                                     │
│  [BGP 会话数] [接口利用率] [CPU/内存]            │
└──────────────────────────────────────────────────┘
```

### 4. 执行历史 (Phase 2+)

**需后端支持**：PostgreSQL checkpointer 已存储会话

```
┌──────────────────────────────────────────────────┐
│  📜 执行历史                    [导出 CSV]       │
├──────────────────────────────────────────────────┤
│  筛选: [全部工作流 ▼] [本周 ▼] [🔍 搜索...]     │
├──────────────────────────────────────────────────┤
│  │ 时间           │ 类型     │ 用户    │ 状态 │  │
│  ├────────────────┼──────────┼─────────┼──────┤  │
│  │ 11-30 10:23    │ Query    │ admin   │ ✅   │  │
│  │ 11-30 09:15    │ Execute  │ operator│ ✅   │  │
│  │ 11-29 16:42    │ DeepDive │ admin   │ ❌   │  │
│  │ 11-29 14:20    │ NetBox   │ operator│ ✅   │  │
└──────────────────────────────────────────────────┘
```

---

## Feature Priority Matrix

| 功能 | 用户价值 | 后端依赖 | 复杂度 | 优先级 |
|------|----------|----------|--------|--------|
| Token 认证 | 高 | 无 | 低 | **P0** |
| Chat + SSE | 高 | 已有 | 中 | **P0** |
| HITL 审批 | 高 | 已有 | 中 | **P1** |
| 报告阅读 | 中 | 已有数据 | 低 | **P2** |
| 执行历史 | 中 | 需 API | 中 | **P2** |
| 巡检配置 | 中 | 需 API | 中 | **P3** |
| 网络拓扑 | 中 | 需集成 | 高 | **P3** |
| 文档上传 | 低 | 需 API + ETL | 高 | **P4** |

---

## Token 获取方式

### 方式 1: 服务器启动日志

启动 OLAV 服务器后，Token 会自动打印到控制台：

```bash
uv run python -m olav.server.app
# 或 Docker 模式
docker-compose up olav-server

# 控制台输出:
# ============================================================
# 🔑 ACCESS TOKEN (valid for 24 hours):
#    Abc123XyzTokenStringHere...
#
# 🌐 WebGUI URL (click to open):
#    http://localhost:3100?token=Abc123XyzTokenStringHere...
# ============================================================
```

### 方式 2: 环境变量预设

在 Docker 或多副本部署时，可以预设固定 Token：

```bash
# .env
OLAV_API_TOKEN=your-secure-token-here

# docker-compose.yml
services:
  olav-server:
    environment:
      - OLAV_API_TOKEN=${OLAV_API_TOKEN}
```

