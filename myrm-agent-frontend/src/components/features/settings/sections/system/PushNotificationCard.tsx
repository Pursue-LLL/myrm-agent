'use client';

/**
 * [INPUT]
 * - hooks/usePushSubscription
 * - lib/deploy-mode::isTauriRuntime
 *
 * [OUTPUT]
 * - PushNotificationCard: Settings card for Web Push subscription management
 *
 * [POS]
 * UI for enabling/disabling offline push notifications. Only shown in non-Tauri
 * environments (Tauri uses native notifications). Handles unsupported browsers
 * and permission denial gracefully.
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';

import { IconBell } from '@/components/features/icons/PremiumIcons';
import Toggle from '@/components/features/settings/common/Toggle';
import { toast } from '@/lib/utils/toast';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { usePushSubscription, type PushSubscriptionState } from '@/hooks/usePushSubscription';

function stateLabel(state: PushSubscriptionState, t: (key: string) => string): string {
  switch (state) {
    case 'subscribed':
      return t('pushStatus.enabled');
    case 'unsubscribed':
    case 'prompt':
      return t('pushStatus.disabled');
    case 'denied':
      return t('pushStatus.denied');
    case 'unsupported':
      return t('pushStatus.unsupported');
  }
}

const PushNotificationCard = memo(() => {
  const t = useTranslations('settings.system');
  const { state, loading, error, subscribe, unsubscribe, sendTest } = usePushSubscription();

  if (isTauriRuntime()) return null;
  if (state === 'unsupported') return null;

  const isEnabled = state === 'subscribed';
  const canToggle = state !== 'denied';

  const handleToggle = async () => {
    try {
      if (isEnabled) {
        await unsubscribe();
        toast.success(t('pushDisabled'));
      } else {
        await subscribe();
        toast.success(t('pushEnabled'));
      }
    } catch {
      // error state is managed by the hook
    }
  };

  const handleTest = async () => {
    try {
      await sendTest();
      toast.success(t('pushTestSent'));
    } catch {
      // error state is managed by the hook
    }
  };

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3 px-2">
        <IconBell className="w-5 h-5 text-muted-foreground" />
        <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">
          {t('push.title')}
        </h2>
      </div>

      <div className="p-5 rounded-2xl border border-border/50 bg-card/50 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="space-y-1 min-w-0">
            <p className="text-sm font-bold text-foreground">{t('push.label')}</p>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {t('push.description')}
            </p>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            {isEnabled && (
              <button
                type="button"
                onClick={() => void handleTest()}
                className="px-3 py-1 text-xs font-medium rounded-lg bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 transition-colors"
              >
                {t('push.test')}
              </button>
            )}

            <Toggle
              checked={isEnabled}
              isLoading={loading}
              disabled={!canToggle}
              onChange={() => void handleToggle()}
              size="sm"
              ariaLabel={stateLabel(state, t)}
            />
          </div>
        </div>

        {state === 'denied' && (
          <p className="text-xs text-destructive">{t('push.deniedHint')}</p>
        )}

        {error && (
          <p className="text-xs text-destructive">{error}</p>
        )}
      </div>
    </section>
  );
});

PushNotificationCard.displayName = 'PushNotificationCard';

export default PushNotificationCard;
