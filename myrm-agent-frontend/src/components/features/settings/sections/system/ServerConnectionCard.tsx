'use client';

import { memo, useState, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { IconPlug, IconCheck, IconAlertCircle } from '@/components/features/icons/PremiumIcons';
import { isTauriRuntime, getRemoteGatewayConfig, setRemoteGatewayConfig } from '@/lib/deploy-mode';
import { switchRemoteFollow } from '@/lib/remote-follow-switch';
import ActiveSessionsSwitchConfirmDialog from './ActiveSessionsSwitchConfirmDialog';
import {
  addRemoteProfile,
  ensureCloudProfile,
  getActiveRemoteProfileId,
  listRemoteProfiles,
  removeRemoteProfile,
  setActiveRemoteProfileId,
  type RemoteConnectionProfile,
} from '@/lib/remote-profiles';
import { toast } from '@/lib/utils/toast';
import { setLastGood, setPendingSwitch } from '@/lib/connection-switch-guard';
import Toggle from '../../common/Toggle';
import RemoteFirstRunChooser from './RemoteFirstRunChooser';
import ServerConnectionCloudSection from './ServerConnectionCloudSection';
import ServerConnectionRoster from './ServerConnectionRoster';
import { useActiveSessionsGuard } from './useActiveSessionsGuard';
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

  // 切断当前活跃连接前确认：后端有生成中会话时弹窗告知切换会中断它们；取消则复位进行中状态。
  const clearSwitching = useCallback(() => setSwitchingKey(null), []);
  const { guard: guardActiveSessions, dialog: activeSessionsDialog } = useActiveSessionsGuard(clearSwitching);

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

  const handleTestProfile = useCallback(
    (profile: RemoteConnectionProfile) => {
      setTestingId(profile.id);
      void testRemoteHealth(profile.url).then((ok) => {
        setTestingId(null);
        toast[ok ? 'success' : 'error'](ok ? t('testSuccess') : t('testFailed'));
      });
    },
    [t],
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

  // 发现沙箱验证通过后的连接切换：与档案切换同一条路径（先 Rust 编排、成功后才建档案激活）。
  const handleSandboxVerified = useCallback(
    (cpBase: string) => {
      setSwitchingKey('cloud');
      void commitSwitch(
        cpBase,
        () => {
          const profile = ensureCloudProfile(t('cloudProfileName'), cpBase);
          if (!profile) {
            toast.error(t('duplicateProfile'));
            setSwitchingKey(null);
            return;
          }
          setRemoteGatewayConfig({ enabled: true, url: profile.url });
          refresh();
          toast.success(t('connected'));
        },
        true,
      ).then((applied) => {
        if (!applied) {
          setSwitchingKey(null);
        }
      });
    },
    [t, refresh, commitSwitch],
  );

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
          <Toggle
            checked={isRemote}
            onChange={() => {
              if (isRemote) {
                handleDisconnect();
              } else {
                setIsRemote(true);
              }
            }}
            ariaLabel={isRemote ? t('modeRemote') : t('modeLocal')}
          />
        </div>

        {isRemote && (
          <>
            <div className="h-px bg-white/5" />

            {profiles.length > 0 && (
              <ServerConnectionRoster
                profiles={profiles}
                activeId={activeId}
                testingId={testingId}
                switchingKey={switchingKey}
                onTest={handleTestProfile}
                onSelect={handleSelect}
                onRemove={handleRemove}
              />
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

            <ServerConnectionCloudSection
              guardSwitch={guardActiveSessions}
              onSandboxVerified={handleSandboxVerified}
              busy={switchingKey === 'cloud'}
            />
          </>
        )}
      </div>

      <ActiveSessionsSwitchConfirmDialog {...activeSessionsDialog} />
    </section>
  );
});

ServerConnectionCard.displayName = 'ServerConnectionCard';
export default ServerConnectionCard;
