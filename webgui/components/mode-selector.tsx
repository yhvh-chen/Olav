'use client';

import { useState } from 'react';

export type WorkflowMode = 'normal' | 'expert';

interface ModeSelectorProps {
  currentMode: WorkflowMode;
  onModeChange: (mode: WorkflowMode) => void;
}

export function ModeSelector({ currentMode, onModeChange }: ModeSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);

  const modes = [
    {
      id: 'normal' as const,
      name: '标准模式',
      description: '快速查询诊断、设备操作、NetBox 管理',
      icon: '🔍',
    },
    {
      id: 'expert' as const,
      name: '专家模式',
      description: '深度分析、自动分解任务、递归诊断',
      icon: '🧠',
    },
  ];

  const currentModeInfo = modes.find((m) => m.id === currentMode)!;

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-1.5 text-sm hover:bg-secondary"
      >
        <span>{currentModeInfo.icon}</span>
        <span>{currentModeInfo.name}</span>
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
          {/* Backdrop */}
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />

          {/* Dropdown */}
          <div className="absolute right-0 top-full z-20 mt-2 w-64 rounded-lg border border-border bg-background shadow-lg">
            {modes.map((mode) => (
              <button
                key={mode.id}
                onClick={() => {
                  onModeChange(mode.id);
                  setIsOpen(false);
                }}
                className={`flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-secondary ${
                  currentMode === mode.id ? 'bg-secondary/50' : ''
                }`}
              >
                <span className="text-lg">{mode.icon}</span>
                <div>
                  <div className="font-medium">{mode.name}</div>
                  <div className="text-xs text-muted-foreground">{mode.description}</div>
                </div>
                {currentMode === mode.id && (
                  <svg
                    className="ml-auto h-5 w-5 text-green-500"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
