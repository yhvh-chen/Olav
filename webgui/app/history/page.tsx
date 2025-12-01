'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/lib/stores/auth-store';
import { useHistoryStore, filterHistoryItems } from '@/lib/stores/history-store';
import { getHistory, deleteSession } from '@/lib/api/client';
import type { HistoryItem, WorkflowType } from '@/lib/api/types';

// Workflow type labels (Chinese)
const workflowLabels: Record<string, string> = {
  query_diagnostic: '查询诊断',
  device_execution: '设备执行',
  netbox_management: 'NetBox 管理',
  deep_dive: '深度分析',
};

// Workflow type icons
const workflowIcons: Record<string, string> = {
  query_diagnostic: '🔍',
  device_execution: '⚙️',
  netbox_management: '📦',
  deep_dive: '🧠',
};

// Date range labels
const dateRangeLabels: Record<string, string> = {
  all: '全部时间',
  today: '今天',
  week: '最近7天',
  month: '最近30天',
};

export default function HistoryPage() {
  const router = useRouter();
  const { token } = useAuthStore();
  const {
    items,
    total,
    isLoading,
    error,
    filter,
    setItems,
    setLoading,
    setError,
    setFilter,
    clearFilter,
    removeItem,
  } = useHistoryStore();

  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  // Load history on mount
  const loadHistory = useCallback(async () => {
    if (!token) return;
    
    setLoading(true);
    try {
      const response = await getHistory(token, 100, 0);
      setItems(response.sessions, response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载历史失败');
    }
  }, [token, setLoading, setItems, setError]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // Handle session click - navigate to chat with loaded session
  const handleSessionClick = (threadId: string) => {
    router.push(`/chat?session=${threadId}`);
  };

  // Handle delete
  const handleDelete = async (threadId: string) => {
    if (!token) return;
    
    try {
      await deleteSession(threadId, token);
      removeItem(threadId);
      setDeleteConfirm(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败');
    }
  };

  // Export to CSV
  const exportToCSV = () => {
    const filteredItems = filterHistoryItems(items, filter);
    const headers = ['时间', '类型', '首条消息', '消息数'];
    const rows = filteredItems.map((item) => [
      formatDate(item.updated_at),
      workflowLabels[item.workflow_type || ''] || item.workflow_type || '未知',
      `"${(item.first_message || '').replace(/"/g, '""')}"`,
      item.message_count.toString(),
    ]);
    
    const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `olav-history-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Format date for display
  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  // Filter items
  const filteredItems = filterHistoryItems(items, filter);

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-900 via-gray-800 to-gray-900">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-gray-700/50 bg-gray-900/80 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => router.push('/chat')}
                className="text-gray-400 hover:text-white transition-colors"
              >
                ← 返回
              </button>
              <h1 className="text-xl font-semibold text-white flex items-center gap-2">
                📜 执行历史
              </h1>
              <span className="text-sm text-gray-500">
                共 {total} 条记录
              </span>
            </div>
            <button
              onClick={exportToCSV}
              disabled={filteredItems.length === 0}
              className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
            >
              导出 CSV
            </button>
          </div>
        </div>
      </header>

      {/* Filters */}
      <div className="max-w-6xl mx-auto px-4 py-4">
        <div className="flex flex-wrap gap-4 items-center bg-gray-800/50 rounded-lg p-4 border border-gray-700/50">
          {/* Workflow Type Filter */}
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-400">类型:</label>
            <select
              value={filter.workflow_type || 'all'}
              onChange={(e) => setFilter({ workflow_type: e.target.value as WorkflowType | 'all' })}
              className="bg-gray-700 border border-gray-600 rounded-md px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">全部类型</option>
              <option value="query_diagnostic">🔍 查询诊断</option>
              <option value="device_execution">⚙️ 设备执行</option>
              <option value="netbox_management">📦 NetBox 管理</option>
              <option value="deep_dive">🧠 深度分析</option>
            </select>
          </div>

          {/* Date Range Filter */}
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-400">时间:</label>
            <select
              value={filter.date_range || 'all'}
              onChange={(e) => setFilter({ date_range: e.target.value as 'today' | 'week' | 'month' | 'all' })}
              className="bg-gray-700 border border-gray-600 rounded-md px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {Object.entries(dateRangeLabels).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>

          {/* Search */}
          <div className="flex-1 min-w-[200px]">
            <input
              type="text"
              placeholder="搜索消息内容..."
              value={filter.search || ''}
              onChange={(e) => setFilter({ search: e.target.value })}
              className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Clear Filters */}
          {(filter.workflow_type !== 'all' || filter.date_range !== 'all' || filter.search) && (
            <button
              onClick={clearFilter}
              className="text-sm text-gray-400 hover:text-white transition-colors"
            >
              清除筛选
            </button>
          )}
        </div>
      </div>

      {/* History List */}
      <div className="max-w-6xl mx-auto px-4 pb-8">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500" />
          </div>
        ) : error ? (
          <div className="bg-red-900/30 border border-red-700/50 rounded-lg p-4 text-red-400">
            {error}
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            {items.length === 0 ? '暂无执行历史' : '没有匹配的记录'}
          </div>
        ) : (
          <div className="space-y-2">
            {filteredItems.map((item) => (
              <div
                key={item.thread_id}
                className="group relative bg-gray-800/50 hover:bg-gray-800 border border-gray-700/50 hover:border-gray-600 rounded-lg p-4 transition-all cursor-pointer"
                onClick={() => handleSessionClick(item.thread_id)}
              >
                <div className="flex items-start gap-4">
                  {/* Icon */}
                  <div className="text-2xl">
                    {workflowIcons[item.workflow_type || ''] || '💬'}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs px-2 py-0.5 bg-gray-700 rounded text-gray-300">
                        {workflowLabels[item.workflow_type || ''] || item.workflow_type || '未知类型'}
                      </span>
                      <span className="text-xs text-gray-500">
                        {item.message_count} 条消息
                      </span>
                    </div>
                    <p className="text-white truncate">
                      {item.first_message || '（无消息内容）'}
                    </p>
                  </div>

                  {/* Time & Actions */}
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-gray-500">
                      {formatDate(item.updated_at)}
                    </span>
                    
                    {/* Delete Button */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteConfirm(item.thread_id);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1.5 text-gray-500 hover:text-red-400 hover:bg-red-900/30 rounded transition-all"
                      title="删除"
                    >
                      🗑️
                    </button>
                  </div>
                </div>

                {/* Delete Confirmation */}
                {deleteConfirm === item.thread_id && (
                  <div
                    className="absolute inset-0 bg-gray-900/95 rounded-lg flex items-center justify-center gap-4 z-10"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <span className="text-gray-300">确认删除此会话？</span>
                    <button
                      onClick={() => handleDelete(item.thread_id)}
                      className="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded-md text-sm transition-colors"
                    >
                      删除
                    </button>
                    <button
                      onClick={() => setDeleteConfirm(null)}
                      className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded-md text-sm transition-colors"
                    >
                      取消
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Pagination hint */}
        {filteredItems.length > 0 && filteredItems.length < total && (
          <div className="text-center py-4 text-gray-500 text-sm">
            显示 {filteredItems.length} / {total} 条
          </div>
        )}
      </div>
    </div>
  );
}
