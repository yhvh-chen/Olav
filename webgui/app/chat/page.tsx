'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useChatStore, processStreamEvent } from '@/lib/stores/chat-store';
import { streamWorkflow, getSession } from '@/lib/api/client';
import { useAuthStore } from '@/lib/stores/auth-store';
import { useSessionStore } from '@/lib/stores/session-store';
import { useLanguage } from '@/lib/i18n/context';
import { HITLDialog } from '@/components/hitl-dialog';
import { MessageBubble } from '@/components/message-bubble';
import { SessionSidebar } from '@/components/session-sidebar';
import { ToolsMenu, type ToolType } from '@/components/tools-menu';
import { InspectionModal } from '@/components/inspection-modal';
import { DocumentModal } from '@/components/document-modal';
import { ExecutionLogPanel } from '@/components/execution-log-panel';
import { SettingsPanel } from '@/components/settings-panel';
import type { Message, ThinkingStep, ToolEvent, InterruptEvent } from '@/lib/api/types';

// Thinking Steps Panel Component
function ThinkingPanel({ steps, label }: { steps: ThinkingStep[]; label: string }) {
  if (steps.length === 0) return null;
  
  return (
    <div className="mb-2 rounded-lg border border-yellow-500/20 bg-yellow-500/5 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-yellow-600">
        <span className="animate-pulse">🧠</span>
        <span>{label}</span>
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
function ToolIndicator({ tool, label }: { tool: ToolEvent; label: string }) {
  return (
    <div className="mb-2 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
      <div className="flex items-center gap-2 text-xs">
        <span className="animate-spin">⚙️</span>
        <span className="font-medium text-blue-600">{label}: {tool.name}</span>
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
  const [currentTool, setCurrentTool] = useState<ToolType>('standard');
  const [showInspection, setShowInspection] = useState(false);
  const [showDocuments, setShowDocuments] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  // i18n
  const { language, setLanguage, t } = useLanguage();
  
  // Zustand stores
  const { 
    messages, 
    isStreaming, 
    currentThinking, 
    activeTool,
    toolHistory,
    streamingContent,
    addMessage,
    setMessages,
    setStreaming,
    clearChat,
    setAbortController,
    abortStreaming,
  } = useChatStore();
  
  const { token } = useAuthStore();
  const { addSession } = useSessionStore();

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent, currentThinking]);

  // Load session messages
  const handleSelectSession = useCallback(async (threadId: string) => {
    if (!token) return;
    
    try {
      const sessionDetail = await getSession(threadId, token);
      const loadedMessages: Message[] = sessionDetail.messages.map((m) => ({
        role: m.role,
        content: m.content,
        timestamp: m.timestamp,
      }));
      setMessages(loadedMessages);
    } catch (err) {
      console.error('Failed to load session:', err);
    }
  }, [token, setMessages]);

  // Create new session (clear chat)
  const handleNewSession = useCallback(() => {
    clearChat();
  }, [clearChat]);

  const handleToolSelect = (tool: ToolType) => {
    if (tool === 'inspection') {
      setShowInspection(true);
    } else if (tool === 'documents') {
      setShowDocuments(true);
    } else {
      setCurrentTool(tool);
    }
  };

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

    // Create AbortController for stop functionality
    const abortController = new AbortController();
    setAbortController(abortController);

    try {
      // Convert messages for API
      const apiMessages = [...messages, userMessage].map(m => ({
        role: m.role,
        content: m.content,
      }));

      // Use demo token if not logged in
      const authToken = token || 'demo-token';

      // Stream from backend with abort signal
      for await (const event of streamWorkflow(apiMessages, authToken, undefined, abortController.signal)) {
        processStreamEvent(event);
        
        // Handle interrupt (HITL)
        if (event.type === 'interrupt' && event.interrupt) {
          setPendingInterrupt(event.interrupt);
        }
      }
    } catch (error) {
      // Don't show error for aborted requests
      if (error instanceof Error && error.name === 'AbortError') {
        return;
      }
      console.error('Stream error:', error);
      setStreaming(false);
      addMessage({
        role: 'assistant',
        content: `❌ Error: ${error instanceof Error ? error.message : 'Connection failed, please ensure backend is running'}`,
        timestamp: new Date().toISOString(),
      });
    } finally {
      setAbortController(null);
    }
  };

  const handleHITLResult = (approved: boolean) => {
    setPendingInterrupt(null);
    addMessage({
      role: 'assistant',
      content: approved 
        ? '✅ Operation approved, executing...' 
        : '❌ Operation rejected',
      timestamp: new Date().toISOString(),
    });
  };

  return (
    <div className="flex h-screen bg-background">
      {/* Modals */}
      {showInspection && <InspectionModal onClose={() => setShowInspection(false)} />}
      {showDocuments && <DocumentModal onClose={() => setShowDocuments(false)} />}
      <SettingsPanel 
        isOpen={showSettings} 
        onClose={() => setShowSettings(false)}
      />
      
      {/* HITL Approval Dialog */}
      {pendingInterrupt && (
        <HITLDialog
          interrupt={pendingInterrupt}
          onClose={() => setPendingInterrupt(null)}
          onResult={handleHITLResult}
        />
      )}

      {/* Session Sidebar - always render for collapse functionality */}
      <SessionSidebar
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        isCollapsed={!sidebarOpen}
        onToggleCollapse={() => setSidebarOpen(!sidebarOpen)}
        onOpenSettings={() => setShowSettings(true)}
      />

      {/* Main Chat Area */}
      <div className="flex flex-1 flex-col">
        {/* Header - Clean without sidebar toggle (moved to sidebar) */}
        <header className="border-b border-border px-6 py-3">
          <div className="flex items-center justify-center">
            <h1 className="text-xl font-bold text-primary">{t('chat.title')}</h1>
          </div>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6">
          <div className="mx-auto max-w-3xl space-y-4">
            {messages.length === 0 ? (
              <div className="text-center text-muted-foreground">
                <p className="text-lg">{t('chat.welcome')}</p>
                <p className="mt-2">{t('chat.welcome_subtitle')}</p>
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
                  <ThinkingPanel steps={currentThinking} label={t('tools.thinking_process')} />
                  
                  {/* Active Tool */}
                  {activeTool && <ToolIndicator tool={activeTool} label={t('tools.executing')} />}
                  
                  {/* Streaming Response */}
                  <div className="rounded-lg bg-secondary px-4 py-2 text-secondary-foreground">
                    {streamingContent || (
                      <span className="animate-pulse">{t('chat.thinking')}</span>
                    )}
                  </div>
                </div>
              </div>
            )}
            
            {/* Auto-scroll anchor */}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Execution Log Panel - shows when streaming */}
        {isStreaming && (currentThinking.length > 0 || activeTool || toolHistory.length > 0) && (
          <ExecutionLogPanel
            thinkingSteps={currentThinking}
            activeTool={activeTool}
            toolHistory={toolHistory}
          />
        )}

        {/* Input Area */}
        <div className="p-4 pb-6">
          <div className="mx-auto max-w-3xl rounded-xl border border-input bg-background p-2 shadow-sm focus-within:ring-2 focus-within:ring-ring">
            <form onSubmit={handleSubmit} className="flex items-center gap-2">
              {/* Embedded Mode Selection */}
              <ToolsMenu 
                currentMode={currentTool} 
                onSelect={handleToolSelect} 
                variant="ghost"
                compact={true}
              />
              
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={t('chat.placeholder')}
                className="flex-1 bg-transparent px-2 py-2 text-sm focus:outline-none"
                disabled={isStreaming}
              />
              
              {/* Clear Chat Button */}
              <button
                type="button"
                onClick={clearChat}
                className="rounded-lg p-2 text-muted-foreground hover:bg-secondary hover:text-red-500 transition-colors"
                title="Clear Chat"
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="h-5 w-5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                </svg>
              </button>

              {/* Send/Stop Button */}
              {isStreaming ? (
                <button
                  type="button"
                  onClick={abortStreaming}
                  className="rounded-lg bg-red-500 p-2 text-white hover:bg-red-600 transition-colors"
                  title="Stop Generation"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
                    <path fillRule="evenodd" d="M4.25 3A2.25 2.25 0 002 5.25v9.5A2.25 2.25 0 004.25 17h11.5A2.25 2.25 0 0018 14.75v-9.5A2.25 2.25 0 0015.75 3H4.25z" clipRule="evenodd" />
                  </svg>
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!input.trim()}
                  className="rounded-lg bg-primary p-2 text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
                    <path d="M3.105 2.289a.75.75 0 00-.826.95l1.414 4.925A1.5 1.5 0 005.135 9.25h6.115a.75.75 0 010 1.5H5.135a1.5 1.5 0 00-1.442 1.086l-1.414 4.926a.75.75 0 00.826.95 28.89 28.89 0 0015.293-7.154.75.75 0 000-1.115A28.897 28.897 0 003.105 2.289z" />
                  </svg>
                </button>
              )}
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
