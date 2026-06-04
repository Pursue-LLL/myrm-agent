'use client';

import { useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { useToolApprovalResolve } from '@/hooks/useToolApprovalResolve';

type DecisionType = 'approve' | 'edit' | 'reject';

export default function ToolApprovalExpiryWatcher() {
  const t = useTranslations('toolApproval');
  const { queue, resolveRequest } = useToolApprovalResolve();
  const toastFiredRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (queue.length === 0) {
      return;
    }

    const checkExpired = () => {
      const now = Date.now();
      for (const req of queue) {
        if (req.expiresAt * 1000 <= now && !toastFiredRef.current.has(req.requestId)) {
          toastFiredRef.current.add(req.requestId);
          const behavior = req.timeoutBehavior || 'deny';
          const decision: DecisionType = behavior === 'allow' ? 'approve' : 'reject';
          toast.warning(behavior === 'allow' ? t('timeoutAutoApproved') : t('timeoutAutoDenied'));
          void resolveRequest(req.requestId, decision, {
            feedback: `Auto-${decision === 'approve' ? 'approved' : 'denied'} due to approval timeout`,
          });
        }
      }
    };

    checkExpired();
    const timer = setInterval(checkExpired, 1000);
    return () => clearInterval(timer);
  }, [queue, resolveRequest, t]);

  return null;
}
