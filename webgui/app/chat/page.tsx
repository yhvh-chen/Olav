'use client';

import { useState, useRef, useEffect } from 'react';
import { useChatStore, processStreamEvent } from '@/lib/stores/chat-store';
import { streamWorkflow } from '@/lib/api/client';
import { useAuthStore } from '@/lib/stores/auth-store';
import { HITLDialog } from '@/components/hitl-dialog';
import { MessageBubble } from '@/components/message-bubble';
import { ModeSelector, type WorkflowMode } from '@/components/mode-selector';
import type { Message, ThinkingStep, ToolEvent, InterruptEvent } from '@/lib/api/types';

// Thinking Steps Panel Component
function ThinkingPanel({ steps }: { steps: ThinkingStep[] }) {
  if (steps.length === 0) return null;
  
  return (
    <div className="mb-2 rounded-lg border border-yellow-500/20 bg-yellow-500/5 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-yellow-600">
        <span className="animate-pulse">🧠</span>
        <span>思考过程</span>
      </div>
      <div className="space-y-1 text-xs text-muted-foreground">
        {steps.map((step, i) => (
          <div key={i} className="flex gap-2">
            <span className="text-yellow-600">{step.step}.</span>
            <span>{step.content}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Active Tool Indicator Component
function ToolIndicator({ tool }: { tool: ToolEvent }) {
  return (
    <div className="mb-2 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
      <div className="flex items-center gap-2 text-xs">
        <span className="animate-spin">⚙️</span>
        <span className="font-medium text-blue-600">执行工具: {tool.name}</span>
      </div>
      {tool.args && (
        <pre className="mt-2 overflow-x-auto text-xs text-muted-foreground">
          {JSON.stringify(tool.args, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default function ChatPage() {
  const [input, setInput] = useState('');
  const [pendingInterrupt, setPendingInterrupt] = useState<InterruptEvent | null>(null);
  const [workflowMode, setWorkflowMode] = useState<WorkflowMode>('normal');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  // Zustand stores
  const { 
    messages, 
    isStreaming, 
    currentThinking, 
    activeTool, 
    streamingContent,
    addMessage,
    setStreaming,
    clearChat,
  } = useChatStore();
  
  const { token } = useAuthStore();

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent, currentThinking]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;

    const userMessage: Message = { 
      role: 'user', 
      content: input,
      timestamp: new Date().toISOString(),
    };
    
    addMessage(userMessage);
    setInput('');
    setStreaming(true);

    try {
      // Convert messages for API
      const apiMessages = [...messages, userMessage].map(m => ({
        role: m.role,
        content: m.content,
      }));

      // Use demo token if not logged in
      const authToken = token || 'demo-token';

      // Stream from backend
      for await (const event of streamWorkflow(apiMessages, authToken)) {
        processStreamEvent(event);
        
        // Handle interrupt (HITL)
        if (event.type === 'interrupt' && event.interrupt) {
          setPendingInterrupt(event.interrupt);
        }
      }
    } catch (error) {
      console.error('Stream error:', error);
      setStreaming(false);
      addMessage({
        role: 'assistant',
        content: `❌ 错误: ${error instanceof Error ? error.message : '连接失败，请确保后端服务已启动'}`,
        timestamp: new Date().toISOString(),
      });
    }
  };

  const handleHITLResult = (approved: boolean) => {
    setPendingInterrupt(null);
    addMessage({
      role: 'assistant',
      content: approved 
        ? '✅ 操作已批准，正在执行...' 
        : '❌ 操作已拒绝',
      timestamp: new Date().toISOString(),
    });
  };

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* HITL Approval Dialog */}
      {pendingInterrupt && (
        <HITLDialog
          interrupt={pendingInterrupt}
          onClose={() => setPendingInterrupt(null)}
          onResult={handleHITLResult}
        />
      )}

      {/* Header */}
      <header className="border-b border-border px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-bold">OLAV</h1>
            <ModeSelector currentMode={workflowMode} onModeChange={setWorkflowMode} />
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={clearChat}
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              清空对话
            </button>
          </div>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-3xl space-y-4">
          {messages.length === 0 ? (
            <div className="text-center text-muted-foreground">
              <p className="text-lg">👋 您好！我是 OLAV</p>
              <p className="mt-2">企业网络运维智能助手，请输入您的问题</p>
            </div>
          ) : (
            messages.map((msg, i) => (
              <MessageBubble key={i} message={msg} />
            ))
          )}
          {/* Streaming Content */}
          {isStreaming && (
            <div className="flex justify-start">
              <div className="max-w-[80%] space-y-2">
                {/* Thinking Process */}
                <ThinkingPanel steps={currentThinking} />
                
                {/* Active Tool */}
                {activeTool && <ToolIndicator tool={activeTool} />}
                
                {/* Streaming Response */}
                <div className="rounded-lg bg-secondary px-4 py-2 text-secondary-foreground">
                  {streamingContent || (
                    <span className="animate-pulse">思考中...</span>
                  )}
                </div>
              </div>
            </div>
          )}
          
          {/* Auto-scroll anchor */}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <div className="border-t border-border p-4">
        <form onSubmit={handleSubmit} className="mx-auto max-w-3xl flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="输入您的问题，例如：查询 R1 的 BGP 状态"
            className="flex-1 rounded-lg border border-input bg-background px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            disabled={isStreaming}
          />
          <button
            type="submit"
            disabled={isStreaming || !input.trim()}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            发送
          </button>
        </form>
      </div>
    </div>
  );
}
