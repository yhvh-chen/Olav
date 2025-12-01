/**
 * Zustand Store - Chat State
 */

import { create } from 'zustand';
import type { Message, ThinkingStep, ToolEvent, StreamEvent } from '@/lib/api/types';

interface ChatState {
  messages: Message[];
  isStreaming: boolean;
  currentThinking: ThinkingStep[];
  activeTool: ToolEvent | null;
  toolHistory: ToolEvent[];
  streamingContent: string;
  abortController: AbortController | null;
  
  addMessage: (message: Message) => void;
  setMessages: (messages: Message[]) => void;
  updateLastMessage: (content: string) => void;
  setStreaming: (isStreaming: boolean) => void;
  addThinkingStep: (step: ThinkingStep) => void;
  setActiveTool: (tool: ToolEvent | null) => void;
  addToolToHistory: (tool: ToolEvent) => void;
  appendStreamingContent: (content: string) => void;
  finalizeStreaming: () => void;
  clearChat: () => void;
  setAbortController: (controller: AbortController | null) => void;
  abortStreaming: () => void;
}

export const useChatStore = create<ChatState>()((set, get) => ({
  messages: [],
  isStreaming: false,
  currentThinking: [],
  activeTool: null,
  toolHistory: [],
  streamingContent: '',
  abortController: null,

  addMessage: (message: Message) => {
    set((state) => ({
      messages: [...state.messages, message],
    }));
  },

  setMessages: (messages: Message[]) => {
    set({ messages });
  },

  updateLastMessage: (content: string) => {
    set((state) => {
      const messages = [...state.messages];
      if (messages.length > 0) {
        messages[messages.length - 1] = {
          ...messages[messages.length - 1],
          content,
        };
      }
      return { messages };
    });
  },

  setStreaming: (isStreaming: boolean) => {
    set({ 
      isStreaming,
      currentThinking: isStreaming ? [] : get().currentThinking,
      streamingContent: isStreaming ? '' : get().streamingContent,
    });
  },

  addThinkingStep: (step: ThinkingStep) => {
    set((state) => ({
      currentThinking: [...state.currentThinking, step],
    }));
  },

  setActiveTool: (tool: ToolEvent | null) => {
    set({ activeTool: tool });
  },

  addToolToHistory: (tool: ToolEvent) => {
    set((state) => ({
      toolHistory: [...state.toolHistory, tool],
    }));
  },

  appendStreamingContent: (content: string) => {
    set((state) => ({
      streamingContent: state.streamingContent + content,
    }));
  },

  finalizeStreaming: () => {
    const { streamingContent, currentThinking } = get();
    
    if (streamingContent) {
      set((state) => ({
        messages: [
          ...state.messages,
          {
            role: 'assistant' as const,
            content: streamingContent,
            timestamp: new Date().toISOString(),
            metadata: {
              thinking_steps: currentThinking.length > 0 ? currentThinking : undefined,
            },
          },
        ],
        streamingContent: '',
        currentThinking: [],
        toolHistory: [],
        isStreaming: false,
        activeTool: null,
      }));
    } else {
      set({
        isStreaming: false,
        activeTool: null,
        toolHistory: [],
      });
    }
  },

  clearChat: () => {
    set({
      messages: [],
      isStreaming: false,
      currentThinking: [],
      activeTool: null,
      toolHistory: [],
      streamingContent: '',
      abortController: null,
    });
  },

  setAbortController: (controller: AbortController | null) => {
    set({ abortController: controller });
  },

  abortStreaming: () => {
    const { abortController, streamingContent } = get();
    
    // Abort the fetch request
    if (abortController) {
      abortController.abort();
    }
    
    // Add cancelled message if there was partial content
    if (streamingContent) {
      set((state) => ({
        messages: [
          ...state.messages,
          {
            role: 'assistant' as const,
            content: streamingContent + '\n\n⚠️ *Response cancelled by user*',
            timestamp: new Date().toISOString(),
          },
        ],
        streamingContent: '',
        currentThinking: [],
        isStreaming: false,
        activeTool: null,
        abortController: null,
      }));
    } else {
      set({
        streamingContent: '',
        currentThinking: [],
        isStreaming: false,
        activeTool: null,
        abortController: null,
      });
    }
  },
}));

/**
 * Process stream events and update chat store
 */
export function processStreamEvent(event: StreamEvent): void {
  const store = useChatStore.getState();

  switch (event.type) {
    case 'thinking':
      if (event.thinking) {
        store.addThinkingStep(event.thinking);
      }
      break;

    case 'tool_start':
      if (event.tool) {
        store.setActiveTool(event.tool);
      }
      break;

    case 'tool_end':
      // Add completed tool to history before clearing active
      if (store.activeTool) {
        store.addToolToHistory(store.activeTool);
      }
      store.setActiveTool(null);
      break;

    case 'token':
      if (event.content) {
        store.appendStreamingContent(event.content);
      }
      break;

    case 'message':
      // Complete message from LangServe stream
      if (event.content) {
        store.appendStreamingContent(event.content);
        store.finalizeStreaming();
      }
      break;

    case 'data':
      // Raw data event - check for content we can display
      // This handles LangServe's wrapped format
      break;

    case 'done':
      store.finalizeStreaming();
      break;

    case 'error':
      if (event.error) {
        store.appendStreamingContent(`❌ 错误: ${event.error.message}`);
      }
      store.finalizeStreaming();
      break;
  }
}
