'use client';

import { useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { useToolApprovalResolve } from '@/hooks/approval/useToolApprovalResolve';
import type { ToolApprovalRequest } from '@/store/chat/types';
import useToolApprovalStore from '@/store/useToolApprovalStore';

const isAutoApproved = (request: ToolApprovalRequest) => request.timeoutBehavior === 'allow';

export default function ToolApprovalExpiryWatcher() {
  const t = useTranslations('toolApproval');
  const { queue, resolveRequest } = useToolApprovalResolve();
  // Each approval is answered automatically once; if that fails its card stays and the hook has already said so.
  const answeredRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (queue.length === 0) {
      return;
    }

    const answerExpired = async (expired: ToolApprovalRequest[]) => {
      await Promise.all(
        expired.map((request) => {
          const approve = isAutoApproved(request);
          return resolveRequest(request.requestId, approve ? 'approve' : 'reject', {
            feedback: `Auto-${approve ? 'approved' : 'denied'} due to approval timeout`,
          });
        }),
      );

      // Announce only approvals that really left the queue, once per batch.
      const waiting = new Set(useToolApprovalStore.getState().queue.map((request) => request.requestId));
      const announced = new Set<string>();
      for (const request of expired) {
        const group = request.batchId ?? request.requestId;
        if (waiting.has(request.requestId) || announced.has(group)) {
          continue;
        }
        announced.add(group);
        toast.warning(isAutoApproved(request) ? t('timeoutAutoApproved') : t('timeoutAutoDenied'));
      }
    };

    const checkExpired = () => {
      const now = Date.now();
      const expired = queue.filter(
        (request) => request.expiresAt * 1000 <= now && !answeredRef.current.has(request.requestId),
      );
      if (expired.length === 0) {
        return;
      }
      for (const request of expired) {
        answeredRef.current.add(request.requestId);
      }
      void answerExpired(expired);
    };

    checkExpired();
    const timer = setInterval(checkExpired, 1000);
    return () => clearInterval(timer);
  }, [queue, resolveRequest, t]);

  return null;
}
