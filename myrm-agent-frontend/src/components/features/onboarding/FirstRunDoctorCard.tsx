'use client';

import { memo, useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { IconCheck, IconAlertCircle } from '@/components/features/icons/PremiumIcons';
import { checkBackendReadyOnce } from '@/lib/backend-health';
import { fetchEntitlements } from '@/lib/cp-billing';
import { isSandbox } from '@/lib/deploy-mode';
import useProviderStore from '@/store/useProviderStore';
import { hasUsableProviderAuth } from '@/store/config/providerTypes';
import { cn } from '@/lib/utils/classnameUtils';
import type { OnboardingDeployChoice } from '@/lib/onboarding-deploy-choice';

/**
 * [POS]
 * 首 30 分钟 Doctor 聚合卡：只读探针（模型可用/后端可达/配额），一键修深链。
 * 配额仅云沙箱探测；本地模式为天然通过态。无写副作用。
 */

type RowState = 'pending' | 'ok' | 'fail';

interface DoctorRows {
  provider: RowState;
  backend: RowState;
  quota: RowState;
}

const ALL_ROWS: (keyof DoctorRows)[] = ['provider', 'backend', 'quota'];

const ROW_ROUTES = {
  provider: '/settings/models',
  backend: '/settings/system',
  quota: '/pricing',
} as const;

interface FirstRunDoctorCardProps {
  deployChoice?: OnboardingDeployChoice | null;
}

const FirstRunDoctorCard = memo(({ deployChoice }: FirstRunDoctorCardProps) => {
  const t = useTranslations('boot.onboarding.doctor');
  const router = useRouter();
  const providers = useProviderStore((s) => s.providers);
  const isInitialized = useProviderStore((s) => s.isInitialized);
  const [rows, setRows] = useState<DoctorRows>({ provider: 'pending', backend: 'pending', quota: 'pending' });

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      const providerOk =
        isInitialized && providers.some((p) => p.isEnabled && hasUsableProviderAuth(p));

      let backendOk = false;
      try {
        backendOk = await checkBackendReadyOnce();
      } catch {
        backendOk = false;
      }

      let quotaOk = true;
      if (isSandbox() && typeof window !== 'undefined') {
        try {
          const token = window.localStorage.getItem('auth_token');
          if (token) {
            const entitlements = await fetchEntitlements(token);
            quotaOk = entitlements.balance_wu + entitlements.subscription_wu > 0;
          }
        } catch {
          quotaOk = false;
        }
      }

      if (!cancelled) {
        setRows({
          provider: providerOk ? 'ok' : 'fail',
          backend: backendOk ? 'ok' : 'fail',
          quota: quotaOk ? 'ok' : 'fail',
        });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [providers, isInitialized]);

  const handleFix = useCallback(
    (row: keyof DoctorRows) => {
      router.push(ROW_ROUTES[row]);
    },
    [router],
  );

  return (
    <div className="space-y-2">
      {deployChoice && deployChoice !== 'local' && (
        <p className="text-xs text-muted-foreground/70">
          {t(deployChoice === 'cloud' ? 'contextCloud' : 'contextRemote')}
        </p>
      )}
      {ALL_ROWS.map((row) => {
        const state = rows[row];
        return (
          <div
            key={row}
            className="flex flex-col gap-2 rounded-2xl border border-white/10 p-3 sm:flex-row sm:items-center"
          >
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-2 text-sm font-bold text-foreground">
                {state === 'ok' && <IconCheck className="w-4 h-4 text-emerald-400" />}
                {state === 'fail' && <IconAlertCircle className="w-4 h-4 text-destructive" />}
                {state === 'pending' && (
                  <span className="w-4 h-4 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                )}
                {t(`rows.${row}.title`)}
              </p>
              <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                {t(`rows.${row}.${state === 'ok' ? 'okHint' : state === 'fail' ? 'failHint' : 'pendingHint'}`)}
              </p>
            </div>
            {state === 'fail' && (
              <button
                type="button"
                onClick={() => handleFix(row)}
                className="px-3 py-1.5 rounded-lg bg-indigo-500 text-white text-xs font-bold hover:bg-indigo-600 transition-colors shrink-0"
              >
                {t('fix')}
              </button>
            )}
          </div>
        );
      })}
      <p
        className={cn(
          'text-xs',
          rows.provider === 'ok' && rows.backend === 'ok' && rows.quota === 'ok'
            ? 'text-emerald-400'
            : 'text-muted-foreground/70',
        )}
      >
        {rows.provider === 'ok' && rows.backend === 'ok' && rows.quota === 'ok'
          ? t('allClear')
          : t('hasIssues')}
      </p>
    </div>
  );
});

FirstRunDoctorCard.displayName = 'FirstRunDoctorCard';
export default FirstRunDoctorCard;
