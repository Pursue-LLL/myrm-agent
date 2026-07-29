'use client';

import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';

export default function BrainConsoleRedirectPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const t = useTranslations('settings.wiki');

  useEffect(() => {
    const agentId = searchParams.get('agentId');
    const target = agentId ? `/settings/wiki?agentId=${encodeURIComponent(agentId)}` : '/settings/wiki';
    router.replace(target);
  }, [router, searchParams]);

  return (
    <div className="flex min-h-[40vh] items-center justify-center px-4 text-sm text-muted-foreground">
      {t('loading')}
    </div>
  );
}
