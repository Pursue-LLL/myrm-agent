'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { AlertCircle } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import useProviderStore from '@/store/useProviderStore';

const NoProviderBanner = memo(() => {
  const t = useTranslations('chat');
  const router = useRouter();
  const isInitialized = useProviderStore((s) => s.isInitialized);
  const hasEnabledProvider = useProviderStore((s) =>
    s.providers.some(
      (p) => p.isEnabled && (p.apiKeys?.some((k) => k.isActive && k.key) || ['ollama', 'lm_studio'].includes(p.id)),
    ),
  );

  if (!isInitialized || hasEnabledProvider) return null;

  return (
    <div className="flex items-center gap-3 w-full rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-900/50 dark:bg-amber-950/30">
      <AlertCircle className="h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" />
      <span className="flex-1 text-sm text-amber-800 dark:text-amber-300">{t('noProviderBanner')}</span>
      <Button size="sm" variant="outline" onClick={() => router.push('/settings/models')}>
        {t('noProviderAction')}
      </Button>
    </div>
  );
});

NoProviderBanner.displayName = 'NoProviderBanner';

export default NoProviderBanner;
