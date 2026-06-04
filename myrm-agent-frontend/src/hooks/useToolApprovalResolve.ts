'use client';

import { useCallback } from 'react';
import { toast } from 'sonner';
import { useTranslations } from 'next-intl';

import { groupRequestsForBulkResume } from '@/lib/approval/approvalBulkGroups';
import {
  buildApprovalDecision,
  resumeApprovalStream,
  type ToolApprovalResolveExtra,
} from '@/lib/approval/resumeApprovalStream';
import { partitionApprovalQueue } from '@/lib/approval/visualApprovalSurface';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import type { ToolApprovalRequest } from '@/store/chat/types';

type DecisionType = 'approve' | 'edit' | 'reject';

export type { ToolApprovalResolveExtra };

export function useToolApprovalResolve() {
  const t = useTranslations('toolApproval');
  const queue = useToolApprovalStore((state) => state.queue);
  const isLoading = useToolApprovalStore((state) => state.isResolving);
  const batchDecisions = useToolApprovalStore((state) => state.batchDecisions);
  const removeRequest = useToolApprovalStore((state) => state.removeRequest);
  const setResolving = useToolApprovalStore((state) => state.setResolving);
  const clearBatchDecisions = useToolApprovalStore((state) => state.clearBatchDecisions);

  const resolveRequest = useCallback(
    async (requestId: string, decision: DecisionType, extra?: ToolApprovalResolveExtra) => {
      setResolving(true);
      try {
        let request = queue.find((r) => r.requestId === requestId);
        if (!request) return;

        let resumeValue: { decisions: ReturnType<typeof buildApprovalDecision>[] };
        let requestsToRemove: ToolApprovalRequest[] = [request];

        if (request.batchId) {
          const nextDecisions = new Map(batchDecisions);
          nextDecisions.set(requestId, { type: decision, extra });
          useToolApprovalStore.setState({ batchDecisions: nextDecisions });

          const batchRequests = queue.filter((r) => r.batchId === request.batchId);
          const allDecided = batchRequests.every((r) => nextDecisions.has(r.requestId));

          if (!allDecided) {
            toast.info(
              t('batchPending', {
                decided: nextDecisions.size,
                total: batchRequests.length,
              }),
            );
            setResolving(false);
            return;
          }

          const sortedRequests = batchRequests.sort((a, b) => (a.batchIndex ?? 0) - (b.batchIndex ?? 0));
          resumeValue = {
            decisions: sortedRequests.map((r) => {
              const dec = nextDecisions.get(r.requestId)!;
              return buildApprovalDecision(dec.type, dec.extra);
            }),
          };
          request = sortedRequests[0];
          requestsToRemove = batchRequests;
          clearBatchDecisions();
        } else {
          resumeValue = {
            decisions: [buildApprovalDecision(decision, extra)],
          };
        }

        await resumeApprovalStream(request, resumeValue, t('resumeError'));

        for (const req of requestsToRemove) {
          removeRequest(req.requestId);
        }
      } catch (error) {
        console.error('[APPROVAL] Resume failed:', error);
        toast.error(t('resumeError'));
      } finally {
        setResolving(false);
      }
    },
    [batchDecisions, clearBatchDecisions, queue, removeRequest, setResolving, t],
  );

  const runBulkDecision = useCallback(
    async (requests: ToolApprovalRequest[], decision: 'approve' | 'reject') => {
      if (requests.length === 0) {
        return;
      }

      setResolving(true);
      try {
        const groups = groupRequestsForBulkResume(requests);

        for (const group of groups) {
          const resumeValue = {
            decisions: group.map(() =>
              buildApprovalDecision(
                decision,
                decision === 'reject' ? { feedback: 'Batch rejected by user' } : undefined,
              ),
            ),
          };

          await resumeApprovalStream(group[0], resumeValue, t('resumeError'));

          for (const req of group) {
            removeRequest(req.requestId);
          }
        }

        clearBatchDecisions();
      } catch (error) {
        console.error('[APPROVAL] Bulk resume failed:', error);
        toast.error(t('resumeError'));
      } finally {
        setResolving(false);
      }
    },
    [clearBatchDecisions, removeRequest, setResolving, t],
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
