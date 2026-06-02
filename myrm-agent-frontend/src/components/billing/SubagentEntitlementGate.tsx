'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { useFeatureEntitlements } from '@/hooks/useFeatureEntitlements';
import { isSandbox } from '@/lib/deploy-mode';

export default function SubagentEntitlementGate({ children }: { children: React.ReactNode }) {
  const t = useTranslations('billing.gates');
  const { canUseSubagent, isLoading } = useFeatureEntitlements();

  if (!isSandbox() || isLoading || canUseSubagent) {
    return <>{children}</>;
  }

  return (
    <div className="rounded-2xl border border-dashed border-border/70 bg-muted/20 px-5 py-8 text-center space-y-4">
      <p className="text-sm font-medium text-foreground">{t('subagentTitle')}</p>
      <p className="text-sm text-muted-foreground">{t('subagentDescription')}</p>
      <Link
        href="/pricing"
        className="inline-flex items-center justify-center rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
      >
        {t('upgrade')}
      </Link>
    </div>
  );
}
