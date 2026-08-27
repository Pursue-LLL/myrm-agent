'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import useApprovalStore from '@/store/useApprovalStore';
import { Drawer, DrawerContent, DrawerDescription, DrawerHeader, DrawerTitle } from '@/components/primitives/drawer';
import { PolymorphicApprovalCard } from './PolymorphicApprovalCard';
import { BatchHighRiskConfirmDialog } from './BatchHighRiskConfirmDialog';
import { Button } from '@/components/primitives/button';
import { toast } from '@/lib/utils/toast';
import { API_BASE_URL } from '@/lib/api';
import type { ToolApprovalResolveExtra } from '@/lib/approval/approvalDecision';
import { shouldResumeDrawerApproval } from '@/lib/approval/buildDrawerResumeValue';
import { resumeDrawerApprovalStream } from '@/lib/approval/resumeDrawerApprovalStream';
import { ApprovalExpiredError } from '@/lib/approval/resumeApprovalStream';
import { classifyBatchApprovalRisk, type BatchRiskReport } from '@/lib/approval/batchRisk';

export function ApprovalDrawer() {
  const tNotifications = useTranslations('notifications');
  const tToolApproval = useTranslations('toolApproval');
  const { isOpen, queue, closeApproval, closeApprovals, hideDrawer } = useApprovalStore();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [pendingRiskReport, setPendingRiskReport] = useState<BatchRiskReport | null>(null);
  const [isHighRiskDialogOpen, setIsHighRiskDialogOpen] = useState(false);

  const handleResolve = async (
    action: 'approve' | 'reject' | 'edit',
    approvalId: string,
    comment?: string,
    edited_payload?: Record<string, unknown>,
    extra?: ToolApprovalResolveExtra,
  ) => {
    const approval = queue.find((item) => item.approval_id === approvalId);
    setIsSubmitting(true);
    try {
      if (approval && shouldResumeDrawerApproval(approval.action_type)) {
        await resumeDrawerApprovalStream(
          approval,
          action,
          {
            ...extra,
            feedback: extra?.feedback ?? comment,
          },
          tToolApproval('resumeError'),
        );
      }

      const httpDecision = action === 'reject' ? 'reject' : 'approve';
      const response = await fetch(`${API_BASE_URL}/approvals/${approvalId}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          decision: httpDecision,
          comment,
          edited_payload: action === 'edit' ? extra?.edited_args : edited_payload,
          allow_always: extra?.allow_always,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to resolve approval: ${response.status}`);
      }

      closeApproval(approvalId);
    } catch (error) {
      console.error('Error resolving approval:', error);
      if (error instanceof ApprovalExpiredError) {
        toast.warning(tToolApproval('approvalExpired'));
        closeApproval(approvalId);
      } else {
        toast.error(tToolApproval('resolveError'));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const executeBatchResolve = async (
    action: 'approve' | 'reject',
    options?: { confirmHighRisk?: boolean; safeOnly?: boolean; targetIds?: string[] },
  ) => {
    setIsSubmitting(true);
    try {
      const targetIds = options?.targetIds ?? queue.map((a) => a.approval_id);
      const targetApprovals = queue.filter((item) => targetIds.includes(item.approval_id));

      const resumableApprovals = targetApprovals.filter((item) => shouldResumeDrawerApproval(item.action_type));
      for (const approval of resumableApprovals) {
        await resumeDrawerApprovalStream(
          approval,
          action,
          action === 'reject' ? { feedback: 'Batch rejected by user' } : undefined,
          tToolApproval('resumeError'),
        );
      }

      const response = await fetch(`${API_BASE_URL}/approvals/batch-resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          approval_ids: targetIds,
          decision: action,
          confirm_high_risk: options?.confirmHighRisk ?? false,
          safe_only: options?.safeOnly ?? false,
        }),
      });

      if (!response.ok) {
        if (response.status === 409) {
          const errorData = await response.json().catch(() => ({}));
          const report = classifyBatchApprovalRisk(queue);
          setPendingRiskReport(report);
          setIsHighRiskDialogOpen(true);
          return;
        }
        throw new Error(`Failed to batch resolve approvals: ${response.status}`);
      }

      const data = await response.json().catch(() => ({}));
      const resolvedIds = data && Array.isArray(data.resolved_ids) ? data.resolved_ids : targetIds;
      closeApprovals(resolvedIds);
      setIsHighRiskDialogOpen(false);
      setPendingRiskReport(null);
    } catch (error) {
      console.error('Error batch resolving approvals:', error);
      if (error instanceof ApprovalExpiredError) {
        toast.warning(tToolApproval('approvalExpired'));
        const approvalIds = queue.map((a) => a.approval_id);
        closeApprovals(approvalIds);
      } else {
        toast.error(tToolApproval('resolveError'));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleBatchResolve = async (action: 'approve' | 'reject') => {
    if (action === 'approve') {
      const report = classifyBatchApprovalRisk(queue);
      if (report.hasHighRisk) {
        setPendingRiskReport(report);
        setIsHighRiskDialogOpen(true);
        return;
      }
    }
    await executeBatchResolve(action);
  };

  if (queue.length === 0) {
    return null;
  }

  return (
    <Drawer open={isOpen} onOpenChange={(open) => !open && hideDrawer()}>
      <DrawerContent className="max-h-[85vh]">
        <div className="mx-auto w-full max-w-2xl px-4 pb-8 pt-4 flex flex-col gap-4 overflow-y-auto">
          <DrawerHeader className="px-0 flex flex-row items-center justify-between">
            <div>
              <DrawerTitle>
                {queue.length > 1
                  ? tToolApproval('batchTitle', { count: queue.length })
                  : tNotifications('approvalRequired', { actionType: queue[0]?.action_type || '' })}
              </DrawerTitle>
              <DrawerDescription>
                {queue.length > 1
                  ? tNotifications('multipleApprovalsDescription')
                  : queue[0]?.reason || tNotifications('goToApproval')}
              </DrawerDescription>
            </div>
            {queue.length > 1 && (
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => handleBatchResolve('reject')} disabled={isSubmitting}>
                  {tToolApproval('rejectAll')}
                </Button>
                <Button onClick={() => handleBatchResolve('approve')} disabled={isSubmitting}>
                  {tToolApproval('approveAll')}
                </Button>
              </div>
            )}
          </DrawerHeader>

          <div className="flex flex-col gap-4">
            {queue.map((approval) => (
              <PolymorphicApprovalCard
                key={approval.approval_id}
                approval={approval}
                onResolve={(action, comment, edited_payload, extra) =>
                  handleResolve(action, approval.approval_id, comment, edited_payload, extra)
                }
                isSubmitting={isSubmitting}
              />
            ))}
          </div>
        </div>
      </DrawerContent>

      <BatchHighRiskConfirmDialog
        open={isHighRiskDialogOpen}
        onOpenChange={setIsHighRiskDialogOpen}
        report={pendingRiskReport}
        isSubmitting={isSubmitting}
        onConfirmAll={() => executeBatchResolve('approve', { confirmHighRisk: true })}
        onApproveSafeOnly={() => executeBatchResolve('approve', { safeOnly: true })}
      />
    </Drawer>
  );
}
