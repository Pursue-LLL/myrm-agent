'use client';

import { memo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { resolveCpBaseUrl } from '@/lib/cp-base-url';
import { beginDesktopOAuth } from '@/lib/desktop-oauth';
import { desktopBridge } from '@/lib/desktopBridge';
import { toast } from '@/lib/utils/toast';

interface ServerConnectionCloudSectionProps {
  /** 切断当前连接前的知情确认（有进行中会话时弹窗）；登录与发现沙箱都先过它。 */
  guardSwitch: (proceed: () => void) => Promise<void>;
  /** 已验证 token 可用后由父级完成真正的连接切换。 */
  onSandboxVerified: (cpBase: string) => void;
  /** 父级切换连接进行中。 */
  busy: boolean;
}

const ServerConnectionCloudSection = memo((props: ServerConnectionCloudSectionProps) => {
  const { guardSwitch, onSandboxVerified, busy } = props;
  const t = useTranslations('settings.system.serverConnection');

  const [cpBaseInput, setCpBaseInput] = useState(() => {
    try {
      return resolveCpBaseUrl();
    } catch {
      return '';
    }
  });
  const [providers, setProviders] = useState<string[] | null>(null);
  const [providersLoading, setProvidersLoading] = useState(false);
  const [discovering, setDiscovering] = useState(false);

  const handleCheckProviders = useCallback(async () => {
    const cpBase = cpBaseInput.trim().replace(/\/+$/, '');
    if (!cpBase) {
      return;
    }
    setProvidersLoading(true);
    try {
      const res = await fetch(`${cpBase}/api/auth/config`, { cache: 'no-store' });
      if (!res.ok) {
        setProviders([]);
        return;
      }
      const data = (await res.json()) as { oauth_providers?: string[] };
      setProviders(data.oauth_providers ?? []);
    } catch {
      setProviders([]);
    } finally {
      setProvidersLoading(false);
    }
  }, [cpBaseInput]);

  const startSignIn = useCallback(
    async (cpBase: string, provider: string) => {
      try {
        const { redirect, codeChallenge } = await beginDesktopOAuth(cpBase);
        const query = new URLSearchParams({
          redirect,
          code_challenge: codeChallenge,
          code_challenge_method: 'S256',
        });
        const opened = await desktopBridge.openExternal(
          `${cpBase}/api/auth/oauth/${encodeURIComponent(provider)}/authorize?${query.toString()}`,
        );
        if (!opened) {
          toast.error(t('signInStartFailed'));
        }
      } catch {
        toast.error(t('signInStartFailed'));
      }
    },
    [t],
  );

  // 登录回跳后会直接切换连接，所以确认必须在打开浏览器之前完成。
  const handleCloudSignIn = useCallback(
    (provider: string) => {
      const cpBase = cpBaseInput.trim().replace(/\/+$/, '');
      if (!cpBase) {
        return;
      }
      void guardSwitch(() => void startSignIn(cpBase, provider));
    },
    [cpBaseInput, guardSwitch, startSignIn],
  );

  const handleDiscoverSandbox = useCallback(async () => {
    const cpBase = cpBaseInput.trim().replace(/\/+$/, '');
    const token = typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : null;
    if (!token || token === 'local_user_token') {
      toast.error(t('signInFirst'));
      return;
    }
    setDiscovering(true);
    try {
      const res = await fetch(`${cpBase}/api/sandboxes`, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        cache: 'no-store',
      });
      if (!res.ok) {
        toast.error(t('discoverFailed'));
        return;
      }
      void guardSwitch(() => onSandboxVerified(cpBase));
    } catch {
      toast.error(t('discoverFailed'));
    } finally {
      setDiscovering(false);
    }
  }, [cpBaseInput, t, guardSwitch, onSandboxVerified]);

  return (
    <div className="space-y-3">
      <p className="text-sm font-bold text-foreground">{t('cloudTitle')}</p>
      <p className="text-xs text-muted-foreground leading-relaxed">{t('cloudDesc')}</p>
      <input
        type="url"
        value={cpBaseInput}
        onChange={(e) => {
          setCpBaseInput(e.target.value);
          setProviders(null);
        }}
        placeholder="https://app.myrmagent.com"
        className="w-full px-4 py-2.5 bg-black/20 border border-white/10 rounded-xl text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
      />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void handleCheckProviders()}
          disabled={providersLoading || !cpBaseInput.trim()}
          className="px-4 py-2 rounded-xl border border-white/10 text-xs font-bold hover:bg-white/5 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {providersLoading ? t('testing') : t('checkProviders')}
        </button>
        <button
          type="button"
          onClick={() => void handleDiscoverSandbox()}
          disabled={discovering || busy || !cpBaseInput.trim()}
          className="px-4 py-2 rounded-xl border border-white/10 text-xs font-bold hover:bg-white/5 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {discovering ? t('testing') : t('discoverSandbox')}
        </button>
      </div>
      {providers !== null && providers.length === 0 && (
        <p className="text-xs text-muted-foreground/70">{t('providersUnavailable')}</p>
      )}
      {providers !== null && providers.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {providers.map((provider) => (
            <button
              key={provider}
              type="button"
              onClick={() => handleCloudSignIn(provider)}
              className="px-4 py-2.5 rounded-xl bg-indigo-500 text-white text-xs font-bold hover:bg-indigo-600 transition-colors"
            >
              {t('continueWith', { provider })}
            </button>
          ))}
        </div>
      )}
    </div>
  );
});

ServerConnectionCloudSection.displayName = 'ServerConnectionCloudSection';
export default ServerConnectionCloudSection;
