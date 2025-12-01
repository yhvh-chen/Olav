'use client';

import { useState } from 'react';

export type ToolType = 'standard' | 'expert' | 'inspection' | 'documents';

interface ToolsMenuProps {
  currentMode: ToolType;
  onSelect: (tool: ToolType) => void;
  className?: string;
  variant?: 'default' | 'ghost';
  compact?: boolean;
}

export function ToolsMenu({ currentMode, onSelect, className = '', variant = 'default', compact = false }: ToolsMenuProps) {
  const [isOpen, setIsOpen] = useState(false);

  const tools = [
    {
      id: 'standard' as const,
      name: 'Standard Mode',
      description: 'Quick diagnostics, device ops',
      icon: '⚡',
    },
    {
      id: 'expert' as const,
      name: 'Expert Mode',
      description: 'Deep analysis, recursive tasks',
      icon: '🧠',
    },
    {
      id: 'inspection' as const,
      name: 'Inspections',
      description: 'Run and edit inspections',
      icon: '🔍',
    },
    {
      id: 'documents' as const,
      name: 'Documents',
      description: 'Manage knowledge base',
      icon: '📚',
    },
  ];

  const currentTool = tools.find((t) => t.id === currentMode) || tools[0];

  const buttonBaseClass = "flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors";
  const buttonVariantClass = variant === 'default' 
    ? "border border-input bg-background hover:bg-secondary" 
    : "hover:bg-secondary/50";

  return (
    <div className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`${buttonBaseClass} ${buttonVariantClass}`}
        title="Select Tool"
      >
        <span>{currentTool.icon}</span>
        {!compact && <span className="hidden sm:inline">{currentTool.name}</span>}
        <svg
          className={`h-4 w-4 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute bottom-full left-0 z-20 mb-2 w-64 rounded-lg border border-border bg-background shadow-lg">
            {tools.map((tool) => (
              <button
                key={tool.id}
                onClick={() => {
                  onSelect(tool.id);
                  setIsOpen(false);
                }}
                className={`flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-secondary ${
                  currentMode === tool.id ? 'bg-secondary/50' : ''
                }`}
              >
                <span className="text-lg">{tool.icon}</span>
                <div>
                  <div className="font-medium">{tool.name}</div>
                  <div className="text-xs text-muted-foreground">{tool.description}</div>
                </div>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
