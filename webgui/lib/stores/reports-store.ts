/**
 * Reports Store - Zustand state for inspection reports
 */

import { create } from 'zustand';
import type { ReportSummary, ReportDetail } from '@/lib/api/types';

interface ReportsState {
  // List
  reports: ReportSummary[];
  total: number;
  isLoading: boolean;
  error: string | null;
  
  // Detail view
  selectedReport: ReportDetail | null;
  isLoadingDetail: boolean;
  
  // Actions
  setReports: (reports: ReportSummary[], total: number) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setSelectedReport: (report: ReportDetail | null) => void;
  setLoadingDetail: (loading: boolean) => void;
  clearSelection: () => void;
}

export const useReportsStore = create<ReportsState>((set) => ({
  // Initial state
  reports: [],
  total: 0,
  isLoading: false,
  error: null,
  selectedReport: null,
  isLoadingDetail: false,
  
  // Actions
  setReports: (reports, total) => set({ reports, total, error: null }),
  
  setLoading: (isLoading) => set({ isLoading }),
  
  setError: (error) => set({ error, isLoading: false }),
  
  setSelectedReport: (selectedReport) => set({ selectedReport, isLoadingDetail: false }),
  
  setLoadingDetail: (isLoadingDetail) => set({ isLoadingDetail }),
  
  clearSelection: () => set({ selectedReport: null }),
}));
