'use client';

import { memo, useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Bell, BellOff, BellRing, Smartphone } from 'lucide-react';
import { Switch } from '@/components/primitives/switch';
import { Button } from '@/components/primitives/button';
import { useWebPush, type WebPushState } from '@/hooks/useWebPush';
import { usePWAInstall } from '@/hooks/usePWAInstall';
import { toast } from '@/lib/utils/toast';
import { isTauriRuntime } from '@/lib/deploy-mode';

function isIOSSafari(): boolean {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent;
  return /iPad|iPhone|iPod/.test(ua) || (ua.includes('Macintosh') && 'ontouchend' in document);
}

function isStandalone(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(display-mode: standalone)').matches;
}

const StateIcon = memo(({ state }: { state: WebPushState }) => {
  switch (state) {
    case 'subscribed':
      return <BellRing className="h-4 w-4 text-emerald-500" />;
    case 'denied':
      return <BellOff className="h-4 w-4 text-destructive" />;
    default:
      return <Bell className="h-4 w-4 text-muted-foreground" />;
  }
});
StateIcon.displayName = 'StateIcon';

const WebPushCard = memo(function WebPushCard() {
  const t = useTranslations('settings');
  const { state, subscribe, unsubscribe, sendTest } = useWebPush();
  const { isInstalled, isInstallable, promptInstall } = usePWAInstall();
  const [testing, setTesting] = useState(false);

  const isTauri = isTauriRuntime();
  const isIOS = isIOSSafari();
  const needsPWAInstall = isIOS && !isStandalone();

  const handleToggle = useCallback(
    async (checked: boolean) => {
      if (checked) {
        await subscribe();
      } else {
        await unsubscribe();
      }
    },
    [subscribe, unsubscribe],
  );

  const handleTest = useCallback(async () => {
    setTesting(true);
    try {
      const count = await sendTest();
      toast.success(t('webPushTestSent', { count: String(count) }));
    } catch {
      toast.error(t('webPushTestFailed'));
    } finally {
      setTesting(false);
    }
  }, [sendTest, t]);

  if (isTauri) return null;

  if (state === 'unsupported') {
    return (
      <div className="rounded-xl border border-border/40 bg-secondary/20 p-4">
        <div className="flex items-center gap-3">
          <BellOff className="h-4 w-4 text-muted-foreground" />
          <div>
            <p className="text-sm font-medium">{t('webPushTitle')}</p>
            <p className="text-xs text-muted-foreground">{t('webPushUnsupported')}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border/40 bg-secondary/20 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <StateIcon state={state} />
          <div>
            <p className="text-sm font-medium">{t('webPushTitle')}</p>
            <p className="text-xs text-muted-foreground">{t('webPushDesc')}</p>
          </div>
        </div>
        <Switch
          checked={state === 'subscribed'}
          onCheckedChange={(checked) => void handleToggle(checked)}
          disabled={state === 'loading' || state === 'denied'}
        />
      </div>

      {state === 'denied' && (
        <p className="text-xs text-destructive">{t('webPushDenied')}</p>
      )}

      {state === 'subscribed' && (
        <Button
          variant="outline"
          size="sm"
          className="text-xs"
          onClick={() => void handleTest()}
          disabled={testing}
        >
          {testing ? t('webPushTesting') : t('webPushSendTest')}
        </Button>
      )}

      {needsPWAInstall && state !== 'subscribed' && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
          <Smartphone className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
          <div className="text-xs">
            <p className="font-medium text-amber-700 dark:text-amber-400">
              {t('webPushIOSHint')}
            </p>
            {isInstallable && (
              <Button
                variant="link"
                size="sm"
                className="h-auto p-0 text-xs text-amber-600 underline"
                onClick={() => void promptInstall()}
              >
                {t('webPushInstallPWA')}
              </Button>
            )}
          </div>
        </div>
      )}

      {!isInstalled && isInstallable && !needsPWAInstall && state !== 'subscribed' && (
        <div className="flex items-start gap-2 rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 py-2">
          <Smartphone className="h-4 w-4 text-blue-600 mt-0.5 shrink-0" />
          <div className="text-xs">
            <p className="text-blue-700 dark:text-blue-400">
              {t('webPushInstallHint')}
            </p>
            <Button
              variant="link"
              size="sm"
              className="h-auto p-0 text-xs text-blue-600 underline"
              onClick={() => void promptInstall()}
            >
              {t('webPushInstallPWA')}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
});

export default WebPushCard;
