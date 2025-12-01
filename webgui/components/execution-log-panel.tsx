'use client';

import { useState } from 'react';
import { useLanguage } from '@/lib/i18n/context';
import type { ThinkingStep, ToolEvent } from '@/lib/api/types';

interface ExecutionLog {
  id: number;
  timestamp: Date;
  type: 'thinking' | 'tool_start' | 'tool_end' | 'info';
  content: string;
  details?: Record<string, unknown>;
}

interface ExecutionLogPanelProps {
  thinkingSteps: ThinkingStep[];
  activeTool: ToolEvent | null;
  toolHistory: ToolEvent[];
}

export function ExecutionLogPanel({ 
  thinkingSteps, 
  activeTool, 
  toolHistory 
}: ExecutionLogPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const { language, t } = useLanguage();

  // Build log entries from thinking steps and tool events
  const logs: ExecutionLog[] = [];
  let logId = 0;

  // Add thinking steps
  thinkingSteps.forEach((step) => {
    logs.push({
      id: logId++,
      timestamp: new Date(),
      type: 'thinking',
      content: `[${step.step}] ${step.content}`,
    });
  });

  // Add completed tool events
  toolHistory.forEach((tool) => {
    logs.push({
      id: logId++,
      timestamp: new Date(),
      type: 'tool_end',
      content: `✅ ${tool.display_name || tool.name} completed`,
      details: { 
        duration: tool.duration_ms ? `${tool.duration_ms}ms` : undefined,
        success: tool.success,
      },
    });
  });

  // Add active tool if running
  if (activeTool) {
    logs.push({
      id: logId++,
      timestamp: new Date(),
      type: 'tool_start',
      content: `⚙️ ${t('tools.executing')}: ${activeTool.display_name || activeTool.name}`,
      details: activeTool.args,
    });
  }

  const hasLogs = logs.length > 0;

  if (!hasLogs) {
    return null;
  }

  return (
    <div className="border-t border-border bg-background/80 backdrop-blur-sm">
      {/* Toggle Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center justify-between px-4 py-2 text-xs hover:bg-secondary/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className={`transition-transform duration-200 ${isExpanded ? 'rotate-90' : ''}`}>
            ▶
          </span>
          <span className="font-medium text-muted-foreground">
            {t('tools.execution_log')} ({logs.length} {t('tools.events')})
          </span>
          {activeTool && (
            <span className="ml-2 animate-pulse text-blue-500">
              ● {t('tools.running')}
            </span>
          )}
        </div>
        <span className="text-muted-foreground">
          {isExpanded ? t('tools.hide') : t('tools.show')}
        </span>
      </button>

      {/* Log Content */}
      {isExpanded && (
        <div className="max-h-48 overflow-y-auto border-t border-border px-4 py-2">
          <div className="space-y-1 font-mono text-xs">
            {logs.map((log) => (
              <div
                key={log.id}
                className={`flex items-start gap-2 py-1 ${getLogColor(log.type)}`}
              >
                <span className="text-muted-foreground shrink-0">
                  {log.timestamp.toLocaleTimeString(language === 'zh' ? 'zh-CN' : 'en-US', { 
                    hour: '2-digit', 
                    minute: '2-digit', 
                    second: '2-digit',
                    hour12: false,
                  })}
                </span>
                <span className={`shrink-0 ${getTypeBadgeColor(log.type)}`}>
                  {getTypeLabel(log.type)}
                </span>
                <span className="flex-1 break-all">{log.content}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function getLogColor(type: ExecutionLog['type']): string {
  switch (type) {
    case 'thinking':
      return 'text-yellow-500/80';
    case 'tool_start':
      return 'text-blue-500/80';
    case 'tool_end':
      return 'text-green-500/80';
    default:
      return 'text-muted-foreground';
  }
}

function getTypeBadgeColor(type: ExecutionLog['type']): string {
  switch (type) {
    case 'thinking':
      return 'text-yellow-600 bg-yellow-500/10 px-1 rounded';
    case 'tool_start':
      return 'text-blue-600 bg-blue-500/10 px-1 rounded';
    case 'tool_end':
      return 'text-green-600 bg-green-500/10 px-1 rounded';
    default:
      return 'text-muted-foreground';
  }
}

function getTypeLabel(type: ExecutionLog['type']): string {
  switch (type) {
    case 'thinking':
      return 'THINK';
    case 'tool_start':
      return 'EXEC';
    case 'tool_end':
      return 'DONE';
    default:
      return 'INFO';
  }
}
