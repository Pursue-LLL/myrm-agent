'use client';

import { memo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { setRemoteGatewayConfig } from '@/lib/deploy-mode';
import { resolveCpBaseUrl } from '@/lib/cp-base-url';
import {
  addRemoteProfile,
  listRemoteProfiles,
  removeRemoteProfile,
} from '@/lib/remote-profiles';
import { toast } from '@/lib/utils/toast';

const CLOUD_OAUTH_PENDING_KEY = 'myrm-cloud-oauth-pending';

interface ServerConnectionCloudSectionProps {
  onConnected: () => void;
}

const ServerConnectionCloudSection = memo(({ onConnected }: ServerConnectionCloudSectionProps) => {
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

  const handleCloudSignIn = useCallback(
    (provider: string) => {
      const cpBase = cpBaseInput.trim().replace(/\/+$/, '');
      if (!cpBase) {
        return;
      }
      try {
        window.localStorage.setItem(CLOUD_OAUTH_PENDING_KEY, JSON.stringify({ cpBaseUrl: cpBase }));
      } catch {
        // ignore
      }
      const redirect = encodeURIComponent('/auth/oauth/callback?desktop=1');
      window.open(
        `${cpBase}/api/auth/oauth/${provider}/authorize?redirect=${redirect}`,
        '_blank',
        'noopener,noreferrer',
      );
    },
    [cpBaseInput],
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
      const proxyBase = `${cpBase}/proxy/me`;
      let profile = listRemoteProfiles().find((p) => p.url === proxyBase) ?? null;
      if (!profile) {
        profile = addRemoteProfile('Cloud sandbox', proxyBase, { kind: 'cloud', cpBaseUrl: cpBase });
      } else if (profile.kind !== 'cloud') {
        removeRemoteProfile(profile.id);
        profile = addRemoteProfile('Cloud sandbox', proxyBase, { kind: 'cloud', cpBaseUrl: cpBase });
      }
      if (!profile) {
        toast.error(t('duplicateProfile'));
        return;
      }
      setRemoteGatewayConfig({ enabled: true, url: profile.url });
      onConnected();
    } catch {
      toast.error(t('discoverFailed'));
    } finally {
      setDiscovering(false);
    }
  }, [cpBaseInput, t, onConnected]);

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
          disabled={discovering || !cpBaseInput.trim()}
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
