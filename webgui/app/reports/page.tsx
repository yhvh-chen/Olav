'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/lib/stores/auth-store';
import { useReportsStore } from '@/lib/stores/reports-store';
import { getReports, getReport } from '@/lib/api/client';
import type { ReportSummary, ReportDetail } from '@/lib/api/types';

// Status styling
const statusStyles: Record<string, { bg: string; text: string; icon: string }> = {
  '通过': { bg: 'bg-green-900/30', text: 'text-green-400', icon: '✅' },
  '需要关注': { bg: 'bg-yellow-900/30', text: 'text-yellow-400', icon: '🟡' },
  '严重问题': { bg: 'bg-red-900/30', text: 'text-red-400', icon: '🔴' },
  'unknown': { bg: 'bg-gray-900/30', text: 'text-gray-400', icon: '❓' },
};

function getStatusStyle(status: string) {
  return statusStyles[status] || statusStyles['unknown'];
}

// Format date for display
function formatDate(dateStr: string) {
  try {
    const date = new Date(dateStr.replace(' ', 'T'));
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

// Report Card Component
function ReportCard({ 
  report, 
  onClick,
  isSelected,
}: { 
  report: ReportSummary; 
  onClick: () => void;
  isSelected: boolean;
}) {
  const style = getStatusStyle(report.status);
  const passRate = report.pass_count + report.fail_count > 0
    ? Math.round(report.pass_count / (report.pass_count + report.fail_count) * 100)
    : 0;
  
  return (
    <div
      onClick={onClick}
      className={`
        cursor-pointer rounded-lg border p-4 transition-all
        ${isSelected 
          ? 'border-blue-500 bg-blue-900/20' 
          : 'border-gray-700/50 bg-gray-800/50 hover:bg-gray-800 hover:border-gray-600'
        }
      `}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          {/* Config name */}
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs px-2 py-0.5 rounded ${style.bg} ${style.text}`}>
              {style.icon} {report.status}
            </span>
            {report.config_name && (
              <span className="text-xs text-gray-500">
                {report.config_name}
              </span>
            )}
          </div>
          
          {/* Title */}
          <h3 className="text-white font-medium truncate">
            {report.title.replace(/^[🔍📊]\s*/, '')}
          </h3>
          
          {/* Stats */}
          <div className="flex items-center gap-4 mt-2 text-xs text-gray-400">
            <span>📱 {report.device_count} 设备</span>
            <span>📋 {report.check_count} 检查项</span>
            <span className={passRate >= 80 ? 'text-green-400' : passRate >= 50 ? 'text-yellow-400' : 'text-red-400'}>
              {passRate}% 通过
            </span>
          </div>
        </div>
        
        {/* Time */}
        <span className="text-xs text-gray-500 whitespace-nowrap">
          {formatDate(report.executed_at)}
        </span>
      </div>
    </div>
  );
}

// Report Detail Panel Component
function ReportDetailPanel({ 
  report, 
  onClose,
}: { 
  report: ReportDetail; 
  onClose: () => void;
}) {
  const style = getStatusStyle(report.status);
  
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-700/50">
        <div>
          <h2 className="text-lg font-semibold text-white">
            {report.title.replace(/^[🔍📊]\s*/, '')}
          </h2>
          {report.description && (
            <p className="text-sm text-gray-400 mt-1">{report.description}</p>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-white p-2"
        >
          ✕
        </button>
      </div>
      
      {/* Summary Stats */}
      <div className="p-4 border-b border-gray-700/50">
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-gray-800/50 rounded-lg p-3">
            <div className="text-xs text-gray-400 mb-1">执行时间</div>
            <div className="text-white">{report.executed_at}</div>
            {report.duration && (
              <div className="text-xs text-gray-500">耗时: {report.duration}</div>
            )}
          </div>
          <div className={`rounded-lg p-3 ${style.bg}`}>
            <div className="text-xs text-gray-400 mb-1">整体状态</div>
            <div className={`font-medium ${style.text}`}>
              {style.icon} {report.status}
            </div>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <div className="text-xs text-gray-400 mb-1">设备/检查项</div>
            <div className="text-white">
              {report.device_count} 设备 · {report.check_count} 检查项
            </div>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <div className="text-xs text-gray-400 mb-1">通过率</div>
            <div className="flex items-center gap-2">
              <div className="flex-1 bg-gray-700 rounded-full h-2">
                <div 
                  className={`h-2 rounded-full ${
                    report.pass_rate >= 80 ? 'bg-green-500' : 
                    report.pass_rate >= 50 ? 'bg-yellow-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${report.pass_rate}%` }}
                />
              </div>
              <span className="text-white text-sm">{report.pass_rate}%</span>
            </div>
            <div className="text-xs text-gray-500 mt-1">
              ✅ {report.pass_count} 通过 · ❌ {report.fail_count} 失败
            </div>
          </div>
        </div>
      </div>
      
      {/* Warnings */}
      {report.warnings.length > 0 && (
        <div className="p-4 border-b border-gray-700/50">
          <h3 className="text-sm font-medium text-yellow-400 mb-2">
            ⚠️ 警告 ({report.warnings.length})
          </h3>
          <ul className="space-y-1 text-sm text-gray-300">
            {report.warnings.map((warning, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-yellow-500">•</span>
                <span>{warning}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      
      {/* Full Content */}
      <div className="flex-1 overflow-auto p-4">
        <div 
          className="prose prose-invert prose-sm max-w-none"
          dangerouslySetInnerHTML={{ 
            __html: renderMarkdown(report.content) 
          }}
        />
      </div>
    </div>
  );
}

// Simple markdown renderer
function renderMarkdown(md: string): string {
  return md
    // Headers
    .replace(/^### (.+)$/gm, '<h3 class="text-lg font-medium text-white mt-4 mb-2">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-xl font-semibold text-white mt-6 mb-3">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-2xl font-bold text-white mt-6 mb-4">$1</h1>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-white">$1</strong>')
    // Lists
    .replace(/^- (.+)$/gm, '<li class="ml-4 text-gray-300">$1</li>')
    // Tables (simplified)
    .replace(/\|(.+)\|/g, (match) => {
      const cells = match.split('|').filter(c => c.trim());
      if (cells.every(c => /^-+$/.test(c.trim()))) {
        return ''; // Skip separator row
      }
      const isHeader = !match.includes('✅') && !match.includes('❌') && !match.includes('⚠️');
      const tag = isHeader ? 'th' : 'td';
      const cellClass = isHeader 
        ? 'px-3 py-2 text-left text-gray-400 bg-gray-800/50' 
        : 'px-3 py-2 text-gray-300 border-t border-gray-700/50';
      return `<tr>${cells.map(c => `<${tag} class="${cellClass}">${c.trim()}</${tag}>`).join('')}</tr>`;
    })
    // Wrap tables
    .replace(/(<tr>[\s\S]*?<\/tr>)/g, '<table class="w-full text-sm">$1</table>')
    // Line breaks
    .replace(/\n\n/g, '</p><p class="mb-2 text-gray-300">')
    .replace(/\n/g, '<br/>');
}

export default function ReportsPage() {
  const router = useRouter();
  const { token } = useAuthStore();
  const {
    reports,
    total,
    isLoading,
    error,
    selectedReport,
    isLoadingDetail,
    setReports,
    setLoading,
    setError,
    setSelectedReport,
    setLoadingDetail,
    clearSelection,
  } = useReportsStore();

  // Load reports on mount
  const loadReports = useCallback(async () => {
    if (!token) return;
    
    setLoading(true);
    try {
      const response = await getReports(token, 50, 0);
      setReports(response.reports, response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载报告失败');
    }
  }, [token, setLoading, setReports, setError]);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  // Load report detail
  const handleSelectReport = useCallback(async (reportId: string) => {
    if (!token) return;
    
    // If already selected, close it
    if (selectedReport?.id === reportId) {
      clearSelection();
      return;
    }
    
    setLoadingDetail(true);
    try {
      const detail = await getReport(reportId, token);
      setSelectedReport(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载报告详情失败');
    }
  }, [token, selectedReport, setLoadingDetail, setSelectedReport, setError, clearSelection]);

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-900 via-gray-800 to-gray-900">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-gray-700/50 bg-gray-900/80 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => router.push('/chat')}
                className="text-gray-400 hover:text-white transition-colors"
              >
                ← 返回
              </button>
              <h1 className="text-xl font-semibold text-white flex items-center gap-2">
                📊 巡检报告
              </h1>
              <span className="text-sm text-gray-500">
                共 {total} 份报告
              </span>
            </div>
            <button
              onClick={loadReports}
              disabled={isLoading}
              className="px-4 py-2 text-sm bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white rounded-lg transition-colors"
            >
              🔄 刷新
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500" />
          </div>
        ) : error ? (
          <div className="bg-red-900/30 border border-red-700/50 rounded-lg p-4 text-red-400">
            {error}
          </div>
        ) : reports.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            暂无巡检报告
          </div>
        ) : (
          <div className="flex gap-6">
            {/* Report List */}
            <div className={`space-y-3 ${selectedReport ? 'w-1/2' : 'w-full'} transition-all`}>
              {reports.map((report) => (
                <ReportCard
                  key={report.id}
                  report={report}
                  onClick={() => handleSelectReport(report.id)}
                  isSelected={selectedReport?.id === report.id}
                />
              ))}
            </div>
            
            {/* Detail Panel */}
            {selectedReport && (
              <div className="w-1/2 bg-gray-800/50 border border-gray-700/50 rounded-lg overflow-hidden sticky top-24 h-[calc(100vh-8rem)]">
                {isLoadingDetail ? (
                  <div className="flex justify-center items-center h-full">
                    <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500" />
                  </div>
                ) : (
                  <ReportDetailPanel
                    report={selectedReport}
                    onClose={clearSelection}
                  />
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
