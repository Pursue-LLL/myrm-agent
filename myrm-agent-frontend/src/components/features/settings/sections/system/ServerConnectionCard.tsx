'use client';

import { memo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconPlug,
  IconCheck,
  IconAlertCircle,
} from '@/components/features/icons/PremiumIcons';
import {
  isTauriRuntime,
  getRemoteGatewayConfig,
  setRemoteGatewayConfig,
} from '@/lib/deploy-mode';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';

type ConnectionTestState = 'idle' | 'testing' | 'success' | 'failed';

async function testRemoteHealth(url: string): Promise<boolean> {
  try {
    const res = await fetch(`${url}/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(8000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

function isValidServerUrl(raw: string): boolean {
  try {
    const u = new URL(raw);
    return u.protocol === 'http:' || u.protocol === 'https:';
  } catch {
    return false;
  }
}

const ServerConnectionCard = memo(() => {
  const t = useTranslations('settings.system.serverConnection');

  const currentConfig = getRemoteGatewayConfig();
  const [isRemote, setIsRemote] = useState(currentConfig !== null);
  const [urlInput, setUrlInput] = useState(currentConfig?.url ?? '');
  const [testState, setTestState] = useState<ConnectionTestState>('idle');

  const handleTest = useCallback(async () => {
    const trimmed = urlInput.trim().replace(/\/+$/, '');
    if (!isValidServerUrl(trimmed)) {
      toast.error(t('invalidUrl'));
      return;
    }
    setTestState('testing');
    const ok = await testRemoteHealth(trimmed);
    setTestState(ok ? 'success' : 'failed');
    toast[ok ? 'success' : 'error'](ok ? t('testSuccess') : t('testFailed'));
  }, [urlInput, t]);

  const handleConnect = useCallback(() => {
    const trimmed = urlInput.trim().replace(/\/+$/, '');
    if (!isValidServerUrl(trimmed)) {
      toast.error(t('invalidUrl'));
      return;
    }
    setRemoteGatewayConfig({ enabled: true, url: trimmed });
    toast.success(t('connected'));
    window.location.reload();
  }, [urlInput, t]);

  const handleDisconnect = useCallback(() => {
    setRemoteGatewayConfig(null);
    setIsRemote(false);
    setUrlInput('');
    setTestState('idle');
    toast.success(t('disconnected'));
    window.location.reload();
  }, [t]);

  if (!isTauriRuntime()) {
    return null;
  }

  return (
    <section className="space-y-6">
      <div className="flex items-center gap-3 px-2">
        <IconPlug className="w-5 h-5 text-muted-foreground" />
        <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">
          {t('title')}
        </h2>
      </div>

      <div className="space-y-6 p-8 rounded-[2.5rem] bg-white/5 border border-white/10">
        <p className="text-xs text-muted-foreground leading-relaxed">{t('description')}</p>

        {/* Mode toggle */}
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <label className="text-sm font-bold text-foreground">
              {isRemote ? t('modeRemote') : t('modeLocal')}
            </label>
            <p className="text-xs text-muted-foreground">
              {isRemote ? t('remoteDesc') : t('localDesc')}
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              if (isRemote) {
                handleDisconnect();
              } else {
                setIsRemote(true);
              }
            }}
            className={cn(
              'relative w-12 h-6 rounded-full transition-colors',
              isRemote ? 'bg-indigo-500' : 'bg-white/10',
            )}
          >
            <div
              className={cn(
                'absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform',
                isRemote && 'translate-x-6',
              )}
            />
          </button>
        </div>

        {/* Remote URL input & actions */}
        {isRemote && (
          <>
            <div className="h-px bg-white/5" />

            <div className="space-y-3">
              <label className="text-sm font-bold text-foreground">{t('serverUrl')}</label>
              <input
                type="url"
                value={urlInput}
                onChange={(e) => {
                  setUrlInput(e.target.value);
                  setTestState('idle');
                }}
                placeholder={t('serverUrlPlaceholder')}
                className="w-full px-4 py-2.5 bg-black/20 border border-white/10 rounded-xl text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
            </div>

            {/* Test result */}
            {testState === 'success' && (
              <div className="flex items-center gap-2 text-emerald-400 text-xs">
                <IconCheck className="w-4 h-4" />
                {t('testSuccess')}
              </div>
            )}
            {testState === 'failed' && (
              <div className="flex items-center gap-2 text-destructive text-xs">
                <IconAlertCircle className="w-4 h-4" />
                {t('testFailed')}
              </div>
            )}

            <p className="text-xs text-muted-foreground/70">{t('loginRequired')}</p>

            {/* Action buttons */}
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => void handleTest()}
                disabled={testState === 'testing' || !urlInput.trim()}
                className="px-5 py-2.5 rounded-xl border border-white/10 text-sm font-bold hover:bg-white/5 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {testState === 'testing' ? t('testing') : t('testConnection')}
              </button>
              <button
                type="button"
                onClick={handleConnect}
                disabled={!urlInput.trim()}
                className="flex-1 px-5 py-2.5 rounded-xl bg-indigo-500 text-white text-sm font-bold hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {t('save')}
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  );
});

ServerConnectionCard.displayName = 'ServerConnectionCard';
export default ServerConnectionCard;
