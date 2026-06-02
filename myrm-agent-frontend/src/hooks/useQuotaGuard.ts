'use client';

import { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/lib/utils/toast';
import { isSandbox } from '@/lib/deploy-mode';
import { fetchWorkUnitEstimate } from '@/lib/cp-billing';
import useAuthStore from '@/store/useAuthStore';

export interface QuotaCheckResult {
  allowed: boolean;
  reason?: 'chat_limit' | 'search_limit' | 'token_limit' | 'wu_limit';
  estimatedWu?: number;
  remainingWu?: number;
}

export function useQuotaGuard() {
  const sandbox = isSandbox();
  const { token } = useAuthStore();
  const t = useTranslations('billing');

  const validateMessageQuota = useCallback(
    async (messageLength: number, hasAttachments: boolean, actionMode: string): Promise<QuotaCheckResult> => {
      if (!sandbox) {
        return { allowed: true };
      }

      const authToken = token || (typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null);
      if (!authToken) {
        return { allowed: false, reason: 'wu_limit' };
      }

      try {
        const estimate = await fetchWorkUnitEstimate(authToken, {
          message_length: messageLength,
          has_attachments: hasAttachments,
          action_mode: actionMode,
        });

        if (estimate.balance_wu < estimate.estimated_wu) {
          toast.error(t('insufficientWu'));
          return {
            allowed: false,
            reason: 'wu_limit',
            estimatedWu: estimate.estimated_wu,
            remainingWu: estimate.balance_wu,
          };
        }

        toast.info(
          t('estimateToast', {
            wu: estimate.estimated_wu,
            remaining: estimate.remaining_after_wu.toLocaleString(),
          }),
          { duration: 3000 },
        );

        return {
          allowed: true,
          estimatedWu: estimate.estimated_wu,
          remainingWu: estimate.balance_wu,
        };
      } catch {
        toast.error(t('insufficientWu'));
        return { allowed: false, reason: 'wu_limit' };
      }
    },
    [sandbox, token, t],
  );

  const checkChatQuota = useCallback((): QuotaCheckResult => {
    return { allowed: true };
  }, []);

  const checkSearchQuota = useCallback((): QuotaCheckResult => checkChatQuota(), [checkChatQuota]);
  const checkTokenQuota = useCallback((): QuotaCheckResult => checkChatQuota(), [checkChatQuota]);
  const checkAllQuotas = useCallback((): QuotaCheckResult => checkChatQuota(), [checkChatQuota]);

  return {
    checkChatQuota,
    checkSearchQuota,
    checkTokenQuota,
    checkAllQuotas,
    validateMessageQuota,
    isLoading: false,
    skipQuotaCheck: !sandbox,
  };
}

export default useQuotaGuard;
