'use client';

import { useState, useEffect } from 'react';
import { getConfig } from '@/lib/api/client';
import { useLanguage } from '@/lib/i18n/context';
import type { PublicConfig } from '@/lib/api/types';

interface SettingsPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export function SettingsPanel({ isOpen, onClose }: SettingsPanelProps) {
  const { language, setLanguage, t } = useLanguage();
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setIsLoading(true);
      setError(null);
      getConfig()
        .then(setConfig)
        .catch((err) => {
          console.error('Config load error:', err);
          setError(err.message || 'Failed to load configuration');
        })
        .finally(() => setIsLoading(false));
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="mx-4 w-full max-w-md rounded-lg border border-border bg-background shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-lg font-semibold">{t('settings.title')}</h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-6">
          {/* Language Selection */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              {t('settings.language')}
            </label>
            <div className="flex gap-2">
              <button
                onClick={() => setLanguage('en')}
                className={`flex-1 rounded-lg border px-3 py-2 text-sm transition-colors ${
                  language === 'en'
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border hover:bg-secondary'
                }`}
              >
                🇺🇸 English
              </button>
              <button
                onClick={() => setLanguage('zh')}
                className={`flex-1 rounded-lg border px-3 py-2 text-sm transition-colors ${
                  language === 'zh'
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border hover:bg-secondary'
                }`}
              >
                🇨🇳 中文
              </button>
            </div>
          </div>

          {/* LLM Configuration (Read-only) */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              {t('settings.llm_config')}
              <span className="ml-1 text-xs text-muted-foreground">{t('settings.llm_readonly')}</span>
            </label>
            {isLoading ? (
              <div className="rounded-lg border border-border bg-secondary/30 p-3 animate-pulse">
                <div className="h-4 bg-secondary rounded w-3/4 mb-2"></div>
                <div className="h-4 bg-secondary rounded w-1/2"></div>
              </div>
            ) : config ? (
              <div className="rounded-lg border border-border bg-secondary/30 p-3 space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('settings.version')}</span>
                  <span className="font-mono">{config.version}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('settings.environment')}</span>
                  <span className="font-mono">{config.environment}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('settings.expert_mode')}</span>
                  <span className={config.features.expert_mode ? 'text-green-500' : 'text-muted-foreground'}>
                    {config.features.expert_mode ? t('settings.enabled') : t('settings.disabled')}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('settings.agentic_rag')}</span>
                  <span className={config.features.agentic_rag_enabled ? 'text-green-500' : 'text-muted-foreground'}>
                    {config.features.agentic_rag_enabled ? t('settings.enabled') : t('settings.disabled')}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('settings.streaming')}</span>
                  <span className={config.ui.streaming_enabled ? 'text-green-500' : 'text-muted-foreground'}>
                    {config.ui.streaming_enabled ? t('settings.enabled') : t('settings.disabled')}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('settings.workflows')}</span>
                  <span className="font-mono text-xs">{config.workflows.length} {t('settings.available')}</span>
                </div>
              </div>
            ) : error ? (
              <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-sm text-red-500">
                {t('settings.load_failed')}: {error}
              </div>
            ) : null}
          </div>

          {/* Limits info */}
          {config && (
            <div>
              <label className="block text-sm font-medium text-foreground mb-2">
                {t('settings.limits')}
              </label>
              <div className="rounded-lg border border-border bg-secondary/30 p-3 space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('settings.max_query')}</span>
                  <span className="font-mono">{config.limits.max_query_length} {t('settings.chars')}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('settings.session_timeout')}</span>
                  <span className="font-mono">{config.limits.session_timeout_minutes} {t('settings.min')}</span>
                </div>
                {config.limits.rate_limit_rpm && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">{t('settings.rate_limit')}</span>
                    <span className="font-mono">{config.limits.rate_limit_rpm} {t('settings.req_min')}</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-border px-4 py-3">
          <button
            onClick={onClose}
            className="w-full rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            {t('settings.done')}
          </button>
        </div>
      </div>
    </div>
  );
}
