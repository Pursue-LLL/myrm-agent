'use client';

/**
 * Mobile Push Discovery Banner
 *
 * [INPUT]
 * - hooks/pwa/usePushSubscription::usePushSubscription
 * - next-intl::useTranslations
 *
 * [OUTPUT]
 * - MobilePushDiscoveryBanner component
 *
 * [POS]
 * Mobile discoverability banner for Web Push notifications. Prompts mobile users to
 * enable Web Push notifications for offline task completion and approval alerts.
 */

import { useCallback, useState } from 'react';
import { Bell, X } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { usePushSubscription } from '@/hooks/pwa/usePushSubscription';
import { Button } from '@/components/primitives/button';

export function MobilePushDiscoveryBanner() {
  const t = useTranslations('agent.mobileCommand');
  const { state, loading, subscribe } = usePushSubscription();
  const [dismissed, setDismissed] = useState(() => {
    if (typeof window === 'undefined') return false;
    return sessionStorage.getItem('dismissed_mobile_push_banner') === '1';
  });

  const handleDismiss = useCallback(() => {
    setDismissed(true);
    if (typeof window !== 'undefined') {
      sessionStorage.setItem('dismissed_mobile_push_banner', '1');
    }
  }, []);

  const handleSubscribe = useCallback(async () => {
    try {
      await subscribe();
    } catch {
      // Errors handled within usePushSubscription
    }
  }, [subscribe]);

  if (dismissed || (state !== 'prompt' && state !== 'unsubscribed')) {
    return null;
  }

  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-primary/20 bg-primary/5 p-3 backdrop-blur-md shadow-sm">
      <div className="flex items-center gap-2.5 min-w-0">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Bell className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-medium text-foreground leading-snug">{t('pushEnableBanner')}</p>
        </div>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <Button
          type="button"
          size="sm"
          variant="default"
          className="h-7 px-2.5 text-xs font-medium rounded-lg"
          onClick={handleSubscribe}
          disabled={loading}
        >
          {loading ? '...' : t('pushEnableButton')}
        </Button>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="h-7 w-7 rounded-lg text-muted-foreground hover:text-foreground"
          onClick={handleDismiss}
          aria-label={t('pushDismiss')}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
