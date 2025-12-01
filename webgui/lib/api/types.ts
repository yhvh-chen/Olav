/**
 * OLAV API Type Definitions
 * Mirrors backend Pydantic models
 */

// ============================================
// Auth Types (Single Token Mode)
// ============================================
export interface User {
  username: string;
  role: 'admin' | 'operator' | 'viewer';
  disabled: boolean;
}

// Note: No LoginRequest/Token types needed for single-token auth
// Token is obtained from server startup console output

// ============================================
// Config Types
// ============================================
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

// ============================================
// Message Types
// ============================================
export interface Message {
  id?: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
  metadata?: MessageMetadata;
}

export interface MessageMetadata {
  workflow_type?: string;
  tools_used?: string[];
  thinking_steps?: ThinkingStep[];
  duration_ms?: number;
}

// ============================================
// Stream Event Types
// ============================================
export type StreamEventType = 
  | 'token' 
  | 'message'
  | 'thinking' 
  | 'tool_start' 
  | 'tool_end' 
  | 'interrupt' 
  | 'error' 
  | 'done'
  | 'data';  // Raw data from LangServe

export interface StreamEvent {
  type: StreamEventType;
  content?: string;
  thinking?: ThinkingStep;
  tool?: ToolEvent;
  execution_plan?: ExecutionPlan;
  interrupt?: InterruptEvent;
  error?: StreamError;
  data?: Record<string, unknown>;  // Raw LangServe data
}

export interface InterruptEvent {
  thread_id: string;
  operation: string;
  risk_level: 'low' | 'medium' | 'high';
  message: string;
  execution_plan?: ExecutionPlan;
}

export interface ThinkingStep {
  step: 'hypothesis' | 'verification' | 'conclusion' | 'reasoning';
  content: string;
  hypothesis?: string;
  confidence?: number;
  iteration?: number;
}

export interface ToolEvent {
  id: string;
  name: string;
  display_name: string;
  args?: Record<string, unknown>;
  result?: unknown;
  duration_ms?: number;
  success?: boolean;
}

export interface ExecutionPlan {
  id: string;
  device: string;
  operation: string;
  commands: string[];
  risk_level: 'low' | 'medium' | 'high';
}

export interface StreamError {
  code: string;
  message: string;
}

// ============================================
// Health Types
// ============================================
export interface HealthResponse {
  status: 'healthy' | 'degraded';
  version: string;
  environment: string;
  postgres_connected: boolean;
  orchestrator_ready: boolean;
}

// ============================================
// Workflow Types
// ============================================
export type WorkflowType = 
  | 'query_diagnostic' 
  | 'device_execution' 
  | 'netbox_management' 
  | 'deep_dive';

export interface WorkflowResult {
  workflow_type: WorkflowType;
  messages: Message[];
  interrupted: boolean;
  execution_plan?: ExecutionPlan;
  final_message?: string;
}

// ============================================
// Topology Types
// ============================================
export interface TopologyNode {
  id: string;
  hostname: string;
  device_type?: string;
  vendor?: string;
  model?: string;
  status: 'up' | 'down';
  management_ip?: string;
}

export interface TopologyEdge {
  id: string;
  source: string;
  target: string;
  source_port?: string;
  target_port?: string;
  link_type?: string;
}

export interface TopologyData {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  last_updated?: string;
}

// ============================================
// Execution History Types
// ============================================
export interface HistoryItem {
  thread_id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  first_message?: string;
  workflow_type?: WorkflowType | string;
  status?: 'completed' | 'interrupted' | 'failed';
}

export interface HistoryListResponse {
  sessions: HistoryItem[];
  total: number;
}

export interface HistoryFilter {
  workflow_type?: WorkflowType | 'all';
  date_range?: 'today' | 'week' | 'month' | 'all';
  search?: string;
}

// ============================================
// Inspection Report Types
// ============================================
export interface ReportSummary {
  id: string;
  filename: string;
  title: string;
  config_name?: string;
  executed_at: string;
  device_count: number;
  check_count: number;
  pass_count: number;
  fail_count: number;
  status: string;
}

export interface ReportListResponse {
  reports: ReportSummary[];
  total: number;
}

export interface ReportDetail extends ReportSummary {
  content: string;  // Raw markdown content
  description?: string;
  duration?: string;
  pass_rate: number;
  warnings: string[];
}
