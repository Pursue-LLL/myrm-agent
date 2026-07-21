'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { useFeatureEntitlements } from '@/hooks/useFeatureEntitlements';
import { useUpgradeNudgeStore } from '@/store/useUpgradeNudgeStore';
import { isSandbox } from '@/lib/deploy-mode';

export default function CronEntitlementGate({ children }: { children: React.ReactNode }) {
  const t = useTranslations('billing.gates');
  const { canUseCron, isLoading } = useFeatureEntitlements();

  if (!isSandbox() || isLoading || canUseCron) {
    return <>{children}</>;
  }

  const handleUpgradeClick = () => {
    useUpgradeNudgeStore.getState().showFeatureGate('cron');
  };

  return (
    <div className="rounded-2xl border border-dashed border-border/70 bg-muted/20 px-5 py-8 text-center space-y-4">
      <p className="text-sm font-medium text-foreground">{t('cronTitle')}</p>
      <p className="text-sm text-muted-foreground">{t('cronDescription')}</p>
      <button
        onClick={handleUpgradeClick}
        className="inline-flex items-center justify-center rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
      >
        {t('upgrade')}
      </button>
      <Link href="/pricing" className="block text-xs text-muted-foreground hover:underline">
        {t('comparePlans')}
      </Link>
    </div>
  );
}
