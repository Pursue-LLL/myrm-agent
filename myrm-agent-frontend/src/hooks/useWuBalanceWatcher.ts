'use client';

import { useEffect, useRef } from 'react';
import { useEntitlements } from '@/hooks/useEntitlements';
import { useUpgradeNudgeStore } from '@/store/useUpgradeNudgeStore';
import { isSandbox } from '@/lib/deploy-mode';

const LOW_BALANCE_THRESHOLD = 0.2;

/**
 * Watches WU balance and triggers UpgradeNudgeDialog when balance drops below 20%.
 * Only fires once per session to avoid spam.
 */
export function useWuBalanceWatcher() {
  const { entitlements } = useEntitlements();
  const firedRef = useRef(false);

  useEffect(() => {
    if (!isSandbox() || firedRef.current || !entitlements) return;

    const { balance_wu, monthly_allowance_wu } = entitlements;
    if (monthly_allowance_wu <= 0) return;

    const ratio = balance_wu / monthly_allowance_wu;
    if (ratio <= LOW_BALANCE_THRESHOLD && balance_wu > 0) {
      firedRef.current = true;
      useUpgradeNudgeStore.getState().showLowBalance(balance_wu, monthly_allowance_wu);
    }
  }, [entitlements]);
}
