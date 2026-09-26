'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { IconAlertCircle, IconWrench } from '@/components/features/icons/PremiumIcons';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { tauriBackend } from '@/lib/tauri';
import { toast } from '@/lib/utils/toast';

const FAILURE_EVENTS = ['backend-start-failed', 'frontend-start-failed'] as const;
const OFFICIAL_DOWNLOAD_URL = 'https://myrmagent.ai/download';

const RecoveryGuideCard = memo(() => {
  const t = useTranslations('settings.system.recoveryGuide');
  const router = useRouter();
  const [failure, setFailure] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    if (!isTauriRuntime()) {
      return;
    }
    const unlisteners: (() => void)[] = [];
    let cancelled = false;
    void (async () => {
      try {
        const { invoke } = await import('@tauri-apps/api/core');
        const status = await invoke<string>('get_backend_status');
        if (!cancelled && status === 'stopped') {
          setFailure(t('backendStopped'));
        }
      } catch {
        // Best effort: older builds may lack the status command.
      }
      try {
        const { listen } = await import('@tauri-apps/api/event');
        for (const event of FAILURE_EVENTS) {
          const unlisten = await listen<string>(event, (e) => {
            if (!cancelled && typeof e.payload === 'string' && e.payload) {
              setFailure(e.payload);
            } else if (!cancelled) {
              setFailure(event);
            }
          });
          unlisteners.push(unlisten);
        }
      } catch {
        // Best effort: older builds may lack the event bridge.
      }
    })();
    return () => {
      cancelled = true;
      for (const unlisten of unlisteners) {
        unlisten();
      }
    };
  }, []);

  const handleRetry = useCallback(async () => {
    setRetrying(true);
    try {
      await tauriBackend.start();
      toast.success(t('retrySuccess'));
      setFailure(null);
    } catch {
      toast.error(t('retryFailed'));
    } finally {
      setRetrying(false);
    }
  }, [t]);

  if (!isTauriRuntime()) {
    return null;
  }

  return (
    <section className="space-y-6">
      <div className="flex items-center gap-3 px-2">
        <IconWrench className="w-5 h-5 text-muted-foreground" />
        <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">{t('title')}</h2>
      </div>

      <div className="space-y-4 p-8 rounded-[2.5rem] bg-white/5 border border-white/10">
        {failure && (
          <div className="flex items-start gap-2 rounded-2xl border border-destructive/30 bg-destructive/10 p-3">
            <IconAlertCircle className="w-4 h-4 mt-0.5 shrink-0 text-destructive" />
            <p className="text-xs text-destructive/90 leading-relaxed break-all">{failure}</p>
          </div>
        )}
        <p className="text-xs text-muted-foreground leading-relaxed">{t('description')}</p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void handleRetry()}
            disabled={retrying}
            className="px-4 py-2 rounded-xl bg-indigo-500 text-white text-xs font-bold hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {retrying ? t('retrying') : t('retryBackend')}
          </button>
          <button
            type="button"
            onClick={() => router.push('/settings/system?sub=about')}
            className="px-4 py-2 rounded-xl border border-white/10 text-xs font-bold hover:bg-white/5 transition-colors"
          >
            {t('openAbout')}
          </button>
          <a
            href={OFFICIAL_DOWNLOAD_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-2 rounded-xl border border-white/10 text-xs font-bold hover:bg-white/5 transition-colors"
          >
            {t('reinstall')}
          </a>
        </div>
        <p className="text-xs text-muted-foreground/70">{t('dataSafeHint')}</p>
      </div>
    </section>
  );
});

RecoveryGuideCard.displayName = 'RecoveryGuideCard';
export default RecoveryGuideCard;
