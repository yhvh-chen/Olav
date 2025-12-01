'use client';

import { useState } from 'react';
import type { InterruptEvent, ExecutionPlan } from '@/lib/api/types';
import { resumeWorkflow } from '@/lib/api/client';
import { useAuthStore } from '@/lib/stores/auth-store';

interface HITLDialogProps {
  interrupt: InterruptEvent;
  onClose: () => void;
  onResult: (approved: boolean) => void;
}

// Risk level badge colors
const riskColors = {
  low: 'bg-green-500/10 text-green-600 border-green-500/20',
  medium: 'bg-yellow-500/10 text-yellow-600 border-yellow-500/20',
  high: 'bg-red-500/10 text-red-600 border-red-500/20',
};

// Risk level labels
const riskLabels = {
  low: 'Low Risk',
  medium: 'Medium Risk',
  high: 'High Risk',
};

export function HITLDialog({ interrupt, onClose, onResult }: HITLDialogProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);
  const { token } = useAuthStore();

  const handleApprove = async () => {
    setIsSubmitting(true);
    try {
      await resumeWorkflow(interrupt.thread_id, 'approve', token || 'demo-token');
      onResult(true);
    } catch (error) {
      console.error('Approve failed:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!showRejectInput) {
      setShowRejectInput(true);
      return;
    }
    
    setIsSubmitting(true);
    try {
      await resumeWorkflow(interrupt.thread_id, 'reject', token || 'demo-token');
      onResult(false);
    } catch (error) {
      console.error('Reject failed:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg bg-background shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-3">
            <span className="text-2xl">⚠️</span>
            <div>
              <h2 className="text-lg font-semibold">Operation Approval Request</h2>
              <p className="text-sm text-muted-foreground">Your confirmation is required to proceed</p>
            </div>
          </div>
          <span className={`rounded-full border px-3 py-1 text-xs font-medium ${riskColors[interrupt.risk_level]}`}>
            {riskLabels[interrupt.risk_level]}
          </span>
        </div>

        {/* Content */}
        <div className="space-y-4 p-6">
          {/* Operation Description */}
          <div>
            <h3 className="mb-2 text-sm font-medium text-muted-foreground">Operation Description</h3>
            <p className="text-foreground">{interrupt.message}</p>
          </div>

          {/* Execution Plan */}
          {interrupt.execution_plan && (
            <ExecutionPlanDisplay plan={interrupt.execution_plan} />
          )}

          {/* Thread ID (for debugging) */}
          <div className="text-xs text-muted-foreground">
            Thread ID: <code className="rounded bg-secondary px-1">{interrupt.thread_id}</code>
          </div>

          {/* Reject Reason Input */}
          {showRejectInput && (
            <div>
              <label className="mb-2 block text-sm font-medium text-muted-foreground">
                Rejection Reason (Optional)
              </label>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Please explain the reason for rejecting this operation..."
                className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                rows={3}
              />
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3 border-t border-border px-6 py-4">
          <button
            onClick={handleReject}
            disabled={isSubmitting}
            className="rounded-lg border border-red-500/50 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-500/20 disabled:opacity-50"
          >
            {showRejectInput ? 'Confirm Reject' : 'Reject'}
          </button>
          <button
            onClick={handleApprove}
            disabled={isSubmitting}
            className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            {isSubmitting ? 'Processing...' : 'Approve Execution'}
          </button>
        </div>
      </div>
    </div>
  );
}

// Execution Plan Display Component
function ExecutionPlanDisplay({ plan }: { plan: ExecutionPlan }) {
  return (
    <div className="rounded-lg border border-border bg-secondary/30 p-4">
      <h3 className="mb-3 text-sm font-medium text-muted-foreground">Execution Plan</h3>
      
      <div className="space-y-2 text-sm">
        <div className="flex gap-2">
          <span className="text-muted-foreground">Device:</span>
          <span className="font-mono">{plan.device}</span>
        </div>
        <div className="flex gap-2">
          <span className="text-muted-foreground">Operation:</span>
          <span>{plan.operation}</span>
        </div>
        
        {plan.commands.length > 0 && (
          <div>
            <span className="text-muted-foreground">Commands:</span>
            <div className="mt-2 rounded-lg bg-black/50 p-3">
              <pre className="overflow-x-auto text-xs text-green-400">
                {plan.commands.map((cmd, i) => (
                  <div key={i} className="flex gap-2">
                    <span className="text-muted-foreground select-none">$</span>
                    <span>{cmd}</span>
                  </div>
                ))}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
