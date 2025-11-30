'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Message } from '@/lib/api/types';

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2 ${
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'bg-secondary text-secondary-foreground'
        }`}
      >
        {/* Message Content with Markdown */}
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              // Custom rendering for code blocks
              code({ className, children, ...props }) {
                const match = /language-(\w+)/.exec(className || '');
                const isInline = !match;
                
                return isInline ? (
                  <code className="rounded bg-black/20 px-1 py-0.5 text-xs" {...props}>
                    {children}
                  </code>
                ) : (
                  <pre className="overflow-x-auto rounded-lg bg-black/50 p-3">
                    <code className={`language-${match[1]} text-xs`} {...props}>
                      {children}
                    </code>
                  </pre>
                );
              },
              // Custom table styling
              table({ children }) {
                return (
                  <div className="overflow-x-auto">
                    <table className="min-w-full border-collapse text-xs">
                      {children}
                    </table>
                  </div>
                );
              },
              th({ children }) {
                return (
                  <th className="border border-border bg-secondary/50 px-2 py-1 text-left font-medium">
                    {children}
                  </th>
                );
              },
              td({ children }) {
                return (
                  <td className="border border-border px-2 py-1">
                    {children}
                  </td>
                );
              },
              // Links
              a({ children, href }) {
                return (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-500 hover:underline"
                  >
                    {children}
                  </a>
                );
              },
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>
        
        {/* Metadata (if available) */}
        {message.metadata && (
          <div className="mt-2 border-t border-white/10 pt-2">
            {/* Tools Used */}
            {message.metadata.tools_used && message.metadata.tools_used.length > 0 && (
              <div className="flex flex-wrap gap-1 text-xs opacity-70">
                <span>工具:</span>
                {message.metadata.tools_used.map((tool, i) => (
                  <span key={i} className="rounded bg-black/20 px-1">
                    {tool}
                  </span>
                ))}
              </div>
            )}
            
            {/* Duration */}
            {message.metadata.duration_ms && (
              <div className="text-xs opacity-50">
                耗时: {(message.metadata.duration_ms / 1000).toFixed(2)}s
              </div>
            )}
          </div>
        )}
        
        {/* Timestamp */}
        {message.timestamp && (
          <div className="mt-1 text-xs opacity-40">
            {new Date(message.timestamp).toLocaleTimeString('zh-CN')}
          </div>
        )}
      </div>
    </div>
  );
}
