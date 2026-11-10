'use client';

import { useCallback } from 'react';
import { toast } from 'sonner';
import { useTranslations } from 'next-intl';

import { groupRequestsForBulkResume } from '@/lib/approval/approvalBulkGroups';
import { extractDirectoryGrantOptimistic, resumeDecisionsIncludeDirectoryGrant } from '@/lib/approval/approvalDecision';
import {
  buildApprovalDecision,
  resumeApprovalStream,
  type ToolApprovalResolveExtra,
} from '@/lib/approval/resumeApprovalStream';
import { refreshSessionAccessRoots } from '@/lib/sessionAccessRefresh';
import { partitionApprovalQueue } from '@/lib/approval/visualApprovalSurface';
import { isRiskHeldError } from '@/services/riskHeldToast';
import { ApprovalAlreadyResolvedError } from '@/store/chat/streamErrors';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import type { ToolApprovalRequest } from '@/store/chat/types';

type DecisionType = 'approve' | 'edit' | 'reject';

export type { ToolApprovalResolveExtra };

export function useToolApprovalResolve() {
  const t = useTranslations('toolApproval');
  const queue = useToolApprovalStore((state) => state.queue);
  const isLoading = useToolApprovalStore((state) => state.isResolving);
  const removeRequest = useToolApprovalStore((state) => state.removeRequest);
  const setResolving = useToolApprovalStore((state) => state.setResolving);
  const setBatchDecision = useToolApprovalStore((state) => state.setBatchDecision);
  const removeBatchDecisions = useToolApprovalStore((state) => state.removeBatchDecisions);

  const resolveRequest = useCallback(
    async (requestId: string, decision: DecisionType, extra?: ToolApprovalResolveExtra) => {
      setResolving(true);
      let requestsToRemove: ToolApprovalRequest[] = [];
      try {
        // Read the store, not this render's snapshot: approvals answered in the same tick (a whole batch timing out)
        // must see each other's decisions.
        const { queue: pending } = useToolApprovalStore.getState();
        let request = pending.find((r) => r.requestId === requestId);
        if (!request) {
          return;
        }

        let resumeValue: { decisions: ReturnType<typeof buildApprovalDecision>[] };
        requestsToRemove = [request];

        if (request.batchId) {
          const currentBatchId = request.batchId;
          setBatchDecision(requestId, { type: decision, extra });
          const { batchDecisions } = useToolApprovalStore.getState();

          const batchRequests = pending.filter((r) => r.batchId === currentBatchId);
          const decided = batchRequests.filter((r) => batchDecisions.has(r.requestId)).length;

          if (decided < batchRequests.length) {
            toast.info(t('batchPending', { decided, total: batchRequests.length }));
            return;
          }

          const sortedRequests = batchRequests.sort((a, b) => (a.batchIndex ?? 0) - (b.batchIndex ?? 0));
          resumeValue = {
            decisions: sortedRequests.map((r) => {
              const dec = batchDecisions.get(r.requestId);
              if (!dec) {
                throw new Error(`Approval decision missing for request ${r.requestId}`);
              }
              return buildApprovalDecision(dec.type, dec.extra);
            }),
          };
          request = sortedRequests[0];
          requestsToRemove = batchRequests;
          removeBatchDecisions(batchRequests.map((r) => r.requestId));
        } else {
          resumeValue = {
            decisions: [buildApprovalDecision(decision, extra)],
          };
        }

        await resumeApprovalStream(request, resumeValue, t('resumeError'));

        for (const req of requestsToRemove) {
          removeRequest(req.requestId);
        }

        if (resumeDecisionsIncludeDirectoryGrant(resumeValue.decisions) && request.chatId) {
          void refreshSessionAccessRoots(request.chatId, {
            optimistic: extractDirectoryGrantOptimistic(resumeValue.decisions),
          });
        }

        if (decision === 'approve' || decision === 'edit') {
          void import('@/lib/progression/tryMarkMilestone').then(({ tryMarkMilestone }) => {
            tryMarkMilestone('first_approval');
          });
        }
      } catch (error) {
        console.error('[APPROVAL] Resume failed:', error);
        if (error instanceof ApprovalAlreadyResolvedError) {
          toast.warning(t('approvalAlreadyHandled'));
          for (const req of requestsToRemove) {
            removeRequest(req.requestId);
          }
        } else if (!isRiskHeldError(error)) {
          // A reason a risk rule holds has its notice already; the approval stays pending with the reason in its card.
          toast.error(t('resumeError'));
        }
      } finally {
        setResolving(false);
      }
    },
    [removeBatchDecisions, removeRequest, setBatchDecision, setResolving, t],
  );

  const runBulkDecision = useCallback(
    async (requests: ToolApprovalRequest[], decision: 'approve' | 'reject') => {
      if (requests.length === 0) {
        return;
      }

      setResolving(true);
      let answeredElsewhere = false;
      try {
        for (const group of groupRequestsForBulkResume(requests)) {
          const resumeValue = {
            decisions: group.map(() =>
              buildApprovalDecision(
                decision,
                decision === 'reject' ? { feedback: 'Batch rejected by user' } : undefined,
              ),
            ),
          };

          try {
            await resumeApprovalStream(group[0], resumeValue, t('resumeError'));
          } catch (error) {
            // The timeout or another device answered this interrupt first; the other interrupts still wait for us.
            if (!(error instanceof ApprovalAlreadyResolvedError)) {
              throw error;
            }
            answeredElsewhere = true;
          }

          for (const req of group) {
            removeRequest(req.requestId);
          }
        }

        removeBatchDecisions(requests.map((r) => r.requestId));
      } catch (error) {
        console.error('[APPROVAL] Bulk resume failed:', error);
        toast.error(t('resumeError'));
      } finally {
        if (answeredElsewhere) {
          toast.warning(t('approvalAlreadyHandled'));
        }
        setResolving(false);
      }
    },
    [removeBatchDecisions, removeRequest, setResolving, t],
  );

  const approveAll = useCallback(
    async (requests?: ToolApprovalRequest[]) => {
      const target = requests ?? partitionApprovalQueue(queue).modalRequests;
      await runBulkDecision(target, 'approve');
    },
    [queue, runBulkDecision],
  );

  const rejectAll = useCallback(
    async (requests?: ToolApprovalRequest[]) => {
      const target = requests ?? partitionApprovalQueue(queue).modalRequests;
      await runBulkDecision(target, 'reject');
    },
    [queue, runBulkDecision],
  );

  return {
    queue,
    isLoading,
    resolveRequest,
    approveAll,
    rejectAll,
  };
}

export type { ToolApprovalRequest };
