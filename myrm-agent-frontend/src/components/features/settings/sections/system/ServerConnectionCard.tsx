'use client';

import { memo, useState, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { IconPlug, IconCheck, IconAlertCircle } from '@/components/features/icons/PremiumIcons';
import { isTauriRuntime, getRemoteGatewayConfig, setRemoteGatewayConfig } from '@/lib/deploy-mode';
import { switchRemoteFollow } from '@/lib/remote-follow-switch';
import { getActiveSessions } from '@/services/agent';
import ActiveSessionsSwitchConfirmDialog from './ActiveSessionsSwitchConfirmDialog';
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
import { setLastGood, setPendingSwitch } from '@/lib/connection-switch-guard';
import RemoteFirstRunChooser from './RemoteFirstRunChooser';
import ServerConnectionCloudSection from './ServerConnectionCloudSection';
import { testRemoteHealth, useConnectionsRollbackGuard } from './useConnectionsRollbackGuard';

const FIRST_RUN_SEEN_KEY = 'myrm-remote-first-run-seen';

type ConnectionTestState = 'idle' | 'testing' | 'success' | 'failed';

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
  const [profiles, setProfiles] = useState<RemoteConnectionProfile[]>(() => listRemoteProfiles());
  const [activeId, setActiveId] = useState<string | null>(() => getActiveRemoteProfileId());
  const [nameInput, setNameInput] = useState('');
  const [urlInput, setUrlInput] = useState(currentConfig?.url ?? '');
  const [testState, setTestState] = useState<ConnectionTestState>('idle');
  const [testingId, setTestingId] = useState<string | null>(null);
  const [switchingKey, setSwitchingKey] = useState<string | null>(null);
  const [pendingConfirm, setPendingConfirm] = useState<{ count: number; proceed: () => void } | null>(null);
  const [showFirstRun, setShowFirstRun] = useState(
    () => typeof window !== 'undefined' && !window.localStorage.getItem(FIRST_RUN_SEEN_KEY),
  );

  const refresh = useCallback(() => {
    setProfiles(listRemoteProfiles());
    setActiveId(getActiveRemoteProfileId());
  }, []);

  const dismissFirstRun = useCallback(() => {
    try {
      window.localStorage.setItem(FIRST_RUN_SEEN_KEY, '1');
    } catch {
      // ignore
    }
    setShowFirstRun(false);
  }, []);

  const failedUrlRef = useRef<string | null>(null);

  // reload 后 pending 切换复验与回滚（不可达目标恢复 last-good）。
  useConnectionsRollbackGuard({ onRestored: refresh });

  // 切断当前活跃连接前确认：后端有生成中会话时弹窗告知（切换等待其完成
  // 并刷新页面）。查询失败（后端已停/不可达）时放行，避免锁死切换路径。
  const guardActiveSessions = useCallback(async (proceed: () => void): Promise<void> => {
    try {
      const { activeSessions } = await getActiveSessions();
      if (activeSessions.length > 0) {
        setPendingConfirm({ count: activeSessions.length, proceed });
        return;
      }
    } catch {
      // 放行：本地后端不可达本身就是切换动机之一
    }
    proceed();
  }, []);

  const resolvePendingConfirm = useCallback(
    (confirmed: boolean) => {
      // 先取值再 setState：updater 必须保持纯函数（StrictMode 双调不重复执行 proceed）
      const pending = pendingConfirm;
      setPendingConfirm(null);
      if (!pending) {
        return;
      }
      if (confirmed) {
        pending.proceed();
      } else {
        setSwitchingKey(null);
      }
    },
    [pendingConfirm],
  );

  // Health-gated switch commit: unhealthy targets abort unless the user
  // explicitly forces by repeating the same action (manual override).
  // Trusted switches (cloud profiles verified by OAuth/discovery) skip both
  // the probe and the pending record, but still refresh last-good.
  // The Rust-side lifecycle orchestration runs BEFORE apply: on failure the
  // UI state (config/roster) stays untouched and the switch can be retried.
  // Returns true when the switch was applied.
  const commitSwitch = useCallback(
    async (nextUrl: string | null, apply: () => void, trusted = false): Promise<boolean> => {
      if (!trusted && nextUrl !== null) {
        const healthy = await testRemoteHealth(nextUrl);
        if (!healthy) {
          if (failedUrlRef.current === nextUrl) {
            failedUrlRef.current = null;
          } else {
            failedUrlRef.current = nextUrl;
            toast.error(t('gateFailed'));
            return false;
          }
        }
      }
      failedUrlRef.current = null;
      try {
        await switchRemoteFollow(nextUrl !== null);
      } catch {
        toast.error(t('switchFailed'));
        return false;
      }
      const current = getRemoteGatewayConfig();
      setLastGood({ activeId: getActiveRemoteProfileId(), url: current?.url ?? null });
      if (!trusted) {
        setPendingSwitch({ url: nextUrl, at: Date.now() });
      }
      apply();
      return true;
    },
    [t],
  );

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
    setSwitchingKey('add');
    // profile 创建放在确认之后：取消时 roster 不留未连接档案
    void guardActiveSessions(() => {
      const created = addRemoteProfile(name, trimmed);
      if (!created) {
        toast.error(t('duplicateProfile'));
        setSwitchingKey(null);
        return;
      }
      void commitSwitch(created.url, () => {
        setRemoteGatewayConfig({ enabled: true, url: created.url });
        setNameInput('');
        refresh();
        toast.success(t('connected'));
      }).then((applied) => {
        if (!applied) {
          setSwitchingKey(null);
        }
      });
    });
  }, [nameInput, urlInput, t, refresh, commitSwitch, guardActiveSessions]);

  const handleSelect = useCallback(
    (id: string) => {
      const profile = listRemoteProfiles().find((item) => item.id === id) ?? null;
      if (!profile) {
        return;
      }
      // Cloud profiles carry OAuth/discovery verification, so they skip the
      // unauthenticated health probe (same exemption as the test button).
      setSwitchingKey(id);
      void guardActiveSessions(() => {
        void commitSwitch(
          profile.url,
          () => {
            if (!setActiveRemoteProfileId(id)) {
              setSwitchingKey(null);
              return;
            }
            refresh();
            toast.success(t('connected'));
          },
          profile.kind === 'cloud',
        ).then((applied) => {
          if (!applied) {
            setSwitchingKey(null);
          }
        });
      });
    },
    [t, refresh, commitSwitch, guardActiveSessions],
  );

  const handleRemove = useCallback(
    (id: string) => {
      removeRemoteProfile(id);
      refresh();
    },
    [refresh],
  );

  const handleDisconnect = useCallback(() => {
    void commitSwitch(null, () => {
      setRemoteGatewayConfig(null);
      setIsRemote(false);
      setUrlInput('');
      setTestState('idle');
      refresh();
      toast.success(t('disconnected'));
    });
  }, [t, refresh, commitSwitch]);

  const handleCloudConnected = useCallback(async () => {
    refresh();
    toast.success(t('connected'));
    try {
      await switchRemoteFollow(true);
    } catch {
      toast.error(t('switchFailed'));
    }
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

        {showFirstRun && profiles.length === 0 && (
          <RemoteFirstRunChooser
            onSelectLocal={dismissFirstRun}
            onSelectRemote={() => {
              dismissFirstRun();
              setIsRemote(true);
            }}
            onSelectCloud={() => {
              dismissFirstRun();
              setIsRemote(true);
            }}
          />
        )}

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
                      {p.kind !== 'cloud' && (
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
                      )}
                      {p.id !== activeId && (
                        <button
                          type="button"
                          onClick={() => handleSelect(p.id)}
                          disabled={switchingKey === p.id}
                          className="px-3 py-1.5 rounded-lg bg-indigo-500 text-white text-xs font-bold hover:bg-indigo-600 disabled:opacity-50 transition-colors"
                        >
                          {switchingKey === p.id ? t('testing') : t('save')}
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
                disabled={!urlInput.trim() || switchingKey === 'add'}
                className="flex-1 px-5 py-2.5 rounded-xl bg-indigo-500 text-white text-sm font-bold hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {switchingKey === 'add' ? t('testing') : t('save')}
              </button>
            </div>

            <div className="h-px bg-white/5" />

            <ServerConnectionCloudSection onConnected={handleCloudConnected} />
          </>
        )}
      </div>

      <ActiveSessionsSwitchConfirmDialog
        open={pendingConfirm !== null}
        count={pendingConfirm?.count ?? 0}
        onConfirm={() => resolvePendingConfirm(true)}
        onCancel={() => resolvePendingConfirm(false)}
      />
    </section>
  );
});

ServerConnectionCard.displayName = 'ServerConnectionCard';
export default ServerConnectionCard;
