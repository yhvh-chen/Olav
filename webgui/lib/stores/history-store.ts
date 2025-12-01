/**
 * History Store - Zustand state for execution history
 */

import { create } from 'zustand';
import type { HistoryItem, HistoryFilter, WorkflowType } from '@/lib/api/types';

interface HistoryState {
  // Data
  items: HistoryItem[];
  total: number;
  isLoading: boolean;
  error: string | null;
  
  // Filters
  filter: HistoryFilter;
  
  // Actions
  setItems: (items: HistoryItem[], total: number) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setFilter: (filter: Partial<HistoryFilter>) => void;
  clearFilter: () => void;
  removeItem: (threadId: string) => void;
}

const defaultFilter: HistoryFilter = {
  workflow_type: 'all',
  date_range: 'all',
  search: '',
};

export const useHistoryStore = create<HistoryState>((set) => ({
  // Initial state
  items: [],
  total: 0,
  isLoading: false,
  error: null,
  filter: defaultFilter,
  
  // Actions
  setItems: (items, total) => set({ items, total, error: null }),
  
  setLoading: (isLoading) => set({ isLoading }),
  
  setError: (error) => set({ error, isLoading: false }),
  
  setFilter: (newFilter) => set((state) => ({
    filter: { ...state.filter, ...newFilter },
  })),
  
  clearFilter: () => set({ filter: defaultFilter }),
  
  removeItem: (threadId) => set((state) => ({
    items: state.items.filter((item) => item.thread_id !== threadId),
    total: Math.max(0, state.total - 1),
  })),
}));

/**
 * Filter items locally based on current filter state
 */
export function filterHistoryItems(
  items: HistoryItem[],
  filter: HistoryFilter,
): HistoryItem[] {
  return items.filter((item) => {
    // Workflow type filter
    if (filter.workflow_type && filter.workflow_type !== 'all') {
      if (item.workflow_type !== filter.workflow_type) {
        return false;
      }
    }
    
    // Date range filter
    if (filter.date_range && filter.date_range !== 'all') {
      const itemDate = new Date(item.updated_at);
      const now = new Date();
      
      switch (filter.date_range) {
        case 'today': {
          const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
          if (itemDate < todayStart) return false;
          break;
        }
        case 'week': {
          const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
          if (itemDate < weekAgo) return false;
          break;
        }
        case 'month': {
          const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
          if (itemDate < monthAgo) return false;
          break;
        }
      }
    }
    
    // Search filter
    if (filter.search) {
      const searchLower = filter.search.toLowerCase();
      const messageMatch = item.first_message?.toLowerCase().includes(searchLower);
      const typeMatch = item.workflow_type?.toLowerCase().includes(searchLower);
      if (!messageMatch && !typeMatch) {
        return false;
      }
    }
    
    return true;
  });
}
