/**
 * OLAV API Client
 */

import type { 
  User, 
  PublicConfig, 
  HealthResponse, 
  Message,
  StreamEvent,
} from './types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new ApiError(response.status, error.detail || error.message, error.code);
  }

  return response.json();
}

// ============================================
// Auth API (Single Token Mode)
// ============================================
// Note: No login endpoint - token is auto-generated on server startup
// and retrieved from console output or OLAV_API_TOKEN env var

export async function getMe(token: string): Promise<User> {
  return fetchApi<User>('/me', {}, token);
}

// ============================================
// Config API
// ============================================
export async function getConfig(): Promise<PublicConfig> {
  return fetchApi<PublicConfig>('/config');
}

export async function getHealth(): Promise<HealthResponse> {
  return fetchApi<HealthResponse>('/health');
}

// ============================================
// Streaming API
// ============================================

/**
 * Stream workflow execution with enhanced events (thinking, tool calls).
 * Uses /orchestrator/stream/events endpoint for structured events.
 */
export async function* streamWorkflowWithEvents(
  messages: Message[],
  token: string,
  threadId?: string,
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${API_URL}/orchestrator/stream/events`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      input: { messages },
      config: threadId ? { configurable: { thread_id: threadId } } : undefined,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Stream failed' }));
    throw new ApiError(response.status, error.detail);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const event = JSON.parse(line.slice(6)) as StreamEvent;
          yield event;
        } catch {
          // Skip invalid JSON (e.g., ping messages)
        }
      }
    }
  }
}

/**
 * Stream workflow using basic LangServe endpoint.
 * Fallback for simpler streaming without thinking/tool events.
 */
export async function* streamWorkflow(
  messages: Message[],
  token: string,
  threadId?: string,
): AsyncGenerator<StreamEvent> {
  // Use /orchestrator/stream (stateless, LangServe-compatible)
  // NOT /orchestrator/stream/events (requires stateful graph)
  const response = await fetch(`${API_URL}/orchestrator/stream`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      input: { messages },
      config: threadId ? { configurable: { thread_id: threadId } } : undefined,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Stream failed' }));
    throw new ApiError(response.status, error.detail);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      // Handle SSE format: "event: xxx" and "data: xxx"
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6));
          // Convert LangServe format to our StreamEvent format
          yield normalizeStreamEvent(data);
        } catch {
          // Skip invalid JSON (e.g., ping messages)
        }
      }
    }
  }
}

/**
 * Normalize LangServe stream data to our StreamEvent format
 */
function normalizeStreamEvent(data: Record<string, unknown>): StreamEvent {
  // LangServe wraps data in workflow node names like "route_to_workflow"
  // Extract the actual content
  
  // Check for error
  if (data.type === 'error' || data.error) {
    return {
      type: 'error',
      error: {
        code: (data.error as { code?: string })?.code || 'UNKNOWN',
        message: (data.error as { message?: string })?.message || 'Unknown error',
      },
    };
  }

  // Check for workflow output (the actual response)
  for (const key of Object.keys(data)) {
    const nodeData = data[key] as Record<string, unknown>;
    if (nodeData && typeof nodeData === 'object') {
      // Extract messages from workflow output
      const messages = nodeData.messages as Array<{ content: string; type: string }>;
      if (messages && Array.isArray(messages)) {
        // Get the last AI message as the response
        const aiMessages = messages.filter(m => m.type === 'ai');
        if (aiMessages.length > 0) {
          const lastAiMessage = aiMessages[aiMessages.length - 1];
          return {
            type: 'message',
            content: lastAiMessage.content,
          };
        }
      }
      
      // Check for final_message field
      if (typeof nodeData.final_message === 'string') {
        return {
          type: 'message',
          content: nodeData.final_message,
        };
      }
    }
  }

  // Fallback: return as-is for other event types
  return {
    type: 'data',
    data,
  } as unknown as StreamEvent;
}

// ============================================
// HITL API
// ============================================
export async function resumeWorkflow(
  threadId: string,
  decision: 'approve' | 'reject',
  token: string,
): Promise<void> {
  await fetchApi(`/orchestrator/resume/${threadId}`, {
    method: 'POST',
    body: JSON.stringify({ decision }),
  }, token);
}

// ============================================
// Session History API
// ============================================

export interface Session {
  id: string;
  thread_id: string;
  title: string;
  updated_at: string;
  message_count: number;
}

export interface SessionDetail extends Session {
  messages: Array<{
    role: 'user' | 'assistant';
    content: string;
    timestamp?: string;
  }>;
}

/**
 * List all workflow sessions
 */
export async function getSessions(token: string): Promise<Session[]> {
  return fetchApi<Session[]>('/sessions', {}, token);
}

/**
 * Get session details with message history
 */
export async function getSession(threadId: string, token: string): Promise<SessionDetail> {
  return fetchApi<SessionDetail>(`/sessions/${threadId}`, {}, token);
}

/**
 * Delete a session and its checkpoints
 */
export async function deleteSession(threadId: string, token: string): Promise<void> {
  await fetchApi(`/sessions/${threadId}`, { method: 'DELETE' }, token);
}

// ============================================
// Topology API
// ============================================
import type { TopologyData, HistoryListResponse, ReportListResponse, ReportDetail } from './types';

/**
 * Get network topology data
 */
export async function getTopology(token: string): Promise<TopologyData> {
  return fetchApi<TopologyData>('/topology', {}, token);
}

// ============================================
// Execution History API
// ============================================

/**
 * Get execution history with optional pagination
 */
export async function getHistory(
  token: string,
  limit: number = 50,
  offset: number = 0,
): Promise<HistoryListResponse> {
  return fetchApi<HistoryListResponse>(
    `/sessions?limit=${limit}&offset=${offset}`,
    {},
    token,
  );
}

// ============================================
// Inspection Reports API
// ============================================

/**
 * Get list of inspection reports
 */
export async function getReports(
  token: string,
  limit: number = 50,
  offset: number = 0,
): Promise<ReportListResponse> {
  return fetchApi<ReportListResponse>(
    `/reports?limit=${limit}&offset=${offset}`,
    {},
    token,
  );
}

/**
 * Get a specific inspection report by ID
 */
export async function getReport(
  reportId: string,
  token: string,
): Promise<ReportDetail> {
  return fetchApi<ReportDetail>(`/reports/${reportId}`, {}, token);
}

export { ApiError };
