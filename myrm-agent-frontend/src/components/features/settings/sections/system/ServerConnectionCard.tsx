'use client';

import { memo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { IconPlug, IconCheck, IconAlertCircle } from '@/components/features/icons/PremiumIcons';
import { isTauriRuntime, getRemoteGatewayConfig, setRemoteGatewayConfig } from '@/lib/deploy-mode';
import {
  addRemoteProfile,
  getActiveRemoteProfileId,
  listRemoteProfiles,
  removeRemoteProfile,
  setActiveRemoteProfileId,
  type RemoteConnectionProfile,
} from '@/lib/remote-profiles';
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

async function notifyRemoteFollow(deferred: boolean): Promise<void> {
  if (!isTauriRuntime()) {
    return;
  }
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    await invoke('set_remote_follow', { deferred });
    await invoke(deferred ? 'stop_backend' : 'start_backend');
  } catch {
    // Best effort: old builds lack the command, routing still works.
  }
}

const ServerConnectionCard = memo(() => {
  const t = useTranslations('settings.system.serverConnection');

  const currentConfig = getRemoteGatewayConfig();
  const [isRemote, setIsRemote] = useState(currentConfig !== null);
  const [profiles, setProfiles] = useState<RemoteConnectionProfile[]>(() => listRemoteProfiles());
  const [activeId, setActiveId] = useState<string | null>(() => getActiveRemoteProfileId());
  const [nameInput, setNameInput] = useState('');
  const [urlInput, setUrlInput] = useState(currentConfig?.url ?? '');
  const [testState, setTestState] = useState<ConnectionTestState>('idle');
  const [testingId, setTestingId] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setProfiles(listRemoteProfiles());
    setActiveId(getActiveRemoteProfileId());
  }, []);

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

  const handleAddConnect = useCallback(() => {
    const name = nameInput.trim() || 'Remote server';
    const trimmed = urlInput.trim().replace(/\/+$/, '');
    if (!isValidServerUrl(trimmed)) {
      toast.error(t('invalidUrl'));
      return;
    }
    const created = addRemoteProfile(name, trimmed);
    if (!created) {
      toast.error(t('duplicateProfile'));
      return;
    }
    setRemoteGatewayConfig({ enabled: true, url: created.url });
    setNameInput('');
    refresh();
    toast.success(t('connected'));
    void notifyRemoteFollow(true).then(() => window.location.reload());
  }, [nameInput, urlInput, t, refresh]);

  const handleSelect = useCallback(
    (id: string) => {
      if (!setActiveRemoteProfileId(id)) {
        return;
      }
      refresh();
      toast.success(t('connected'));
      void notifyRemoteFollow(true).then(() => window.location.reload());
    },
    [t, refresh],
  );

  const handleRemove = useCallback(
    (id: string) => {
      removeRemoteProfile(id);
      refresh();
    },
    [refresh],
  );

  const handleDisconnect = useCallback(() => {
    setRemoteGatewayConfig(null);
    setIsRemote(false);
    setUrlInput('');
    setTestState('idle');
    refresh();
    toast.success(t('disconnected'));
    void notifyRemoteFollow(false).then(() => window.location.reload());
  }, [t, refresh]);

  if (!isTauriRuntime()) {
    return null;
  }

  return (
    <section className="space-y-6">
      <div className="flex items-center gap-3 px-2">
        <IconPlug className="w-5 h-5 text-muted-foreground" />
        <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">{t('title')}</h2>
      </div>

      <div className="space-y-6 p-8 rounded-[2.5rem] bg-white/5 border border-white/10">
        <p className="text-xs text-muted-foreground leading-relaxed">{t('description')}</p>

        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <label className="text-sm font-bold text-foreground">{isRemote ? t('modeRemote') : t('modeLocal')}</label>
            <p className="text-xs text-muted-foreground">{isRemote ? t('remoteDesc') : t('localDesc')}</p>
          </div>
          <button
            type="button"
            aria-label={isRemote ? t('modeRemote') : t('modeLocal')}
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

        {isRemote && (
          <>
            <div className="h-px bg-white/5" />

            {profiles.length > 0 && (
              <div className="space-y-2">
                {profiles.map((p) => (
                  <div
                    key={p.id}
                    className={cn(
                      'flex flex-col gap-2 rounded-2xl border p-3 sm:flex-row sm:items-center',
                      p.id === activeId ? 'border-indigo-500/50 bg-indigo-500/5' : 'border-white/10',
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-bold text-foreground">{p.name}</p>
                      <p className="truncate text-xs text-muted-foreground">{p.url}</p>
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setTestingId(p.id);
                          void testRemoteHealth(p.url).then((ok) => {
                            setTestingId(null);
                            toast[ok ? 'success' : 'error'](ok ? t('testSuccess') : t('testFailed'));
                          });
                        }}
                        disabled={testingId === p.id}
                        className="px-3 py-1.5 rounded-lg border border-white/10 text-xs font-bold hover:bg-white/5 disabled:opacity-50 transition-colors"
                      >
                        {testingId === p.id ? t('testing') : t('testConnection')}
                      </button>
                      {p.id !== activeId && (
                        <button
                          type="button"
                          onClick={() => handleSelect(p.id)}
                          className="px-3 py-1.5 rounded-lg bg-indigo-500 text-white text-xs font-bold hover:bg-indigo-600 transition-colors"
                        >
                          {t('save')}
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => handleRemove(p.id)}
                        className="px-3 py-1.5 rounded-lg border border-white/10 text-xs font-bold text-muted-foreground hover:bg-white/5 transition-colors"
                      >
                        {t('remove')}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="grid gap-3 sm:grid-cols-[1fr_2fr]">
              <input
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                placeholder={t('profileNamePlaceholder')}
                maxLength={64}
                className="w-full px-4 py-2.5 bg-black/20 border border-white/10 rounded-xl text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
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
            <p className="text-xs text-muted-foreground/70">{t('offlineHint')}</p>

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
                onClick={handleAddConnect}
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
