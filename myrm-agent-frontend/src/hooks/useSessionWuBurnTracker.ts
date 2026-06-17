'use client';

import { useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/lib/utils/toast';
import { isSandbox } from '@/lib/deploy-mode';
import { useEntitlements } from '@/hooks/useEntitlements';

/**
 * Tracks WU balance before a chat task and shows burn delta when the task completes.
 */
export function useSessionWuBurnTracker() {
  const sandbox = isSandbox();
  const { refresh } = useEntitlements();
  const t = useTranslations('billing');
  const balanceBeforeRef = useRef<number | null>(null);

  const markBalanceBeforeSend = useCallback((balanceWu: number) => {
    if (!sandbox) return;
    balanceBeforeRef.current = balanceWu;
  }, [sandbox]);

  const reportBurnAfterTask = useCallback(async () => {
    if (!sandbox || balanceBeforeRef.current === null) return;
    const before = balanceBeforeRef.current;
    balanceBeforeRef.current = null;
    const snapshot = await refresh();
    const after = snapshot?.balance_wu;
    if (after === undefined) return;
    const burned = Math.max(0, before - after);
    if (burned <= 0) return;
    toast.info(t('sessionWuBurn', { wu: burned.toLocaleString(), remaining: after.toLocaleString() }), {
      duration: 5000,
    });
  }, [sandbox, refresh, t]);

  return { markBalanceBeforeSend, reportBurnAfterTask };
}
