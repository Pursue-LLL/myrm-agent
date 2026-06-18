'use client';

import { memo, useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import {
  IconCheck,
  IconCopy,
  IconExternalLink,
  IconGlobe,
  IconLock,
  IconWifi,
  IconWifiOff,
} from '@/components/features/icons/PremiumIcons';
import IngressEntitlementGate from '@/components/billing/IngressEntitlementGate';
import { useIngressRequirement } from '@/hooks/useIngressRequirement';
import { getDocsUrl, isLocalMode, isTauriRuntime } from '@/lib/deploy-mode';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { isValidPublicIngressBaseUrl } from '@/lib/utils/urlUtils';
import { toast } from '@/lib/utils/toast';
import { systemService } from '@/services/system';
import { fetchWebuiProtection } from '@/services/webui-auth';
import { remoteAccessService, type TunnelStatus } from '@/services/remoteAccess';
import { buildMobileHubUrl } from '@/lib/mobileRemote';
import { usePWAInstall } from '@/hooks/usePWAInstall';
import { Button } from '@/components/primitives/button';
import useConfigStore from '@/store/useConfigStore';
import { SystemConfig } from '@/types/system';

function resolveWebuiPort(config: SystemConfig): number {
  if (isTauriRuntime()) {
    return config.webuiPort;
  }
  if (typeof window !== 'undefined' && window.location.port) {
    const parsed = Number.parseInt(window.location.port, 10);
    if (!Number.isNaN(parsed) && parsed > 0) {
      return parsed;
    }
  }
  return config.webuiPort;
}

export const AccessCard = memo<{
  config: SystemConfig;
  localIP: string;
  ingressSnapshot: ReturnType<typeof useIngressRequirement>;
}>(({ config, localIP, ingressSnapshot }) => {
  const t = useTranslations('settings.system');
  const locale = useLocale();
  const [copied, setCopied] = useState<string | null>(null);
  const [testingIngress, setTestingIngress] = useState(false);
  const publicIngressBaseUrl = useConfigStore((s) => s.publicIngressBaseUrl);
  const setPublicIngressBaseUrl = useConfigStore((s) => s.setPublicIngressBaseUrl);

  const accessEnabled = config.enableWebUIMode || (!isTauriRuntime() && isLocalMode());
  const webuiPort = resolveWebuiPort(config);
  const [serverRequirePassword, setServerRequirePassword] = useState<boolean | null>(null);

  useEffect(() => {
    if (isTauriRuntime() || !accessEnabled) {
      return;
    }
    let cancelled = false;
    void fetchWebuiProtection()
      .then((cfg) => {
        if (!cancelled) {
          setServerRequirePassword(cfg.require_password);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setServerRequirePassword(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [accessEnabled]);

  const passwordProtectionEnabled = isTauriRuntime()
    ? config.requirePassword
    : (serverRequirePassword ?? config.requirePassword);
  const showLocalIngress = isLocalMode();
  const ingressResolved = ingressSnapshot !== null;
  const ingressRequired = ingressResolved && ingressSnapshot.required;
  const docsTunnelUrl = getDocsUrl('/guides/tunnel');
  const [lanNetworkUrl, setLanNetworkUrl] = useState('');
  const [tunnelStatus, setTunnelStatus] = useState<TunnelStatus | null>(null);
  const [tunnelBusy, setTunnelBusy] = useState(false);
  const [mobileHubUrl, setMobileHubUrl] = useState('');
  const localeIsZh = locale.startsWith('zh');
  const { isInstallable, isInstalled, promptInstall } = usePWAInstall();

  useEffect(() => {
    if (!showLocalIngress) {
      return;
    }
    let cancelled = false;
    void systemService.getLocalNetwork(webuiPort).then((data) => {
      if (!cancelled && data.url) {
        setLanNetworkUrl(data.url);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [showLocalIngress, webuiPort]);

  const localUrl = `http://localhost:${webuiPort}`;
  const remoteUrl = localIP ? `http://${localIP}:${webuiPort}` : lanNetworkUrl;

  const handleCopy = (text: string, type: string) => {
    writeToClipboard(text);
    setCopied(type);
    toast.success(t('copied'));
    setTimeout(() => setCopied(null), 2000);
  };

  const handleOpen = (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const lanQrSrc = remoteUrl
    ? localIP
      ? `/webui/qrcode.png?host=${localIP}&port=${webuiPort}`
      : `/webui/qrcode.png?url=${encodeURIComponent(remoteUrl)}`
    : '';

  const mobileHubQrSrc = mobileHubUrl
    ? `/webui/qrcode.png?url=${encodeURIComponent(mobileHubUrl)}`
    : '';

  const handleTestIngress = async () => {
    setTestingIngress(true);
    try {
      const ingressUrl = (await systemService.getIngressUrl()) || publicIngressBaseUrl;
      if (!ingressUrl) {
        toast.error(t('access.ingress.notConfigured'));
        return;
      }
      if (!isValidPublicIngressBaseUrl(ingressUrl)) {
        toast.error(t('access.ingress.httpsRequired'));
        return;
      }
      const ok = await systemService.testIngressHealth(ingressUrl);
      if (ok) {
        toast.success(t('access.ingress.testSuccess'));
      } else {
        toast.error(t('access.ingress.testFailed'));
      }
    } catch {
      toast.error(t('access.ingress.testFailed'));
    } finally {
      setTestingIngress(false);
    }
  };

  useEffect(() => {
    if (!showLocalIngress) {
      return;
    }
    let cancelled = false;
    void remoteAccessService.getTunnelStatus().then((status) => {
      if (!cancelled) {
        setTunnelStatus(status);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [showLocalIngress]);

  const handleTunnelToggle = async () => {
    setTunnelBusy(true);
    try {
      const next =
        tunnelStatus?.state === 'running'
          ? await remoteAccessService.stopTunnel()
          : await remoteAccessService.startTunnel(webuiPort);
      setTunnelStatus(next);
      if (next.publicUrl) {
        setPublicIngressBaseUrl(next.publicUrl);
      }
      if (next.state === 'error' && next.error) {
        toast.error(next.error);
      }
    } catch {
      toast.error(t('access.tunnel.error'));
    } finally {
      setTunnelBusy(false);
    }
  };

  const handleShareMobileLink = async () => {
    try {
      const [{ mobilePath }, e2eeKey] = await Promise.all([
        remoteAccessService.createPairingToken(),
        tunnelStatus?.state === 'running' ? remoteAccessService.getE2EEPublicKey() : Promise.resolve(null),
      ]);
      const hubUrl = buildMobileHubUrl(
        mobilePath,
        tunnelStatus?.publicUrl ?? '',
        publicIngressBaseUrl ?? '',
        e2eeKey?.publicKeyB64,
      );
      setMobileHubUrl(hubUrl);
      writeToClipboard(hubUrl);
      toast.success(t('access.tunnel.shareCopied'));
    } catch {
      toast.error(t('access.tunnel.error'));
    }
  };

  useEffect(() => {
    if (
      !showLocalIngress ||
      !passwordProtectionEnabled ||
      tunnelStatus?.state !== 'running' ||
      mobileHubUrl
    ) {
      return;
    }
    let cancelled = false;
    void remoteAccessService.createPairingToken().then(async ({ mobilePath }) => {
      if (cancelled) {
        return;
      }
      let serverKey: string | undefined;
      if (tunnelStatus?.state === 'running') {
        try {
          const keyPayload = await remoteAccessService.getE2EEPublicKey();
          serverKey = keyPayload.publicKeyB64;
        } catch {
          serverKey = undefined;
        }
      }
      setMobileHubUrl(
        buildMobileHubUrl(mobilePath, tunnelStatus.publicUrl ?? '', publicIngressBaseUrl ?? '', serverKey),
      );
    });
    return () => {
      cancelled = true;
    };
  }, [showLocalIngress, passwordProtectionEnabled, tunnelStatus?.state, tunnelStatus?.publicUrl, publicIngressBaseUrl, mobileHubUrl]);

  if (!accessEnabled) {
    return (
      <div className="p-6 rounded-2xl bg-white/5 border border-white/10 text-center text-muted-foreground">
        <IconWifiOff className="w-8 h-8 mx-auto mb-3 opacity-30" />
        <p className="text-sm">{t('access.disabled')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {showLocalIngress && (
        <div className="p-4 rounded-xl bg-indigo-500/10 border border-indigo-500/20 space-y-2">
          <p className="text-sm font-bold text-indigo-300">{t('access.guide.title')}</p>
          <p className="text-xs text-muted-foreground leading-relaxed">{t('access.guide.lanFirst')}</p>
          {ingressResolved &&
            (ingressRequired ? (
              <p className="text-xs text-muted-foreground leading-relaxed">{t('access.guide.publicIngressRequired')}</p>
            ) : (
              <p className="text-xs text-muted-foreground leading-relaxed">{t('access.guide.publicIngressOptional')}</p>
            ))}
        </div>
      )}

      <div className="p-6 rounded-2xl bg-white/5 border border-white/10 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-bold text-foreground">
            <IconGlobe className="w-4 h-4" />
            {t('access.local')}
          </div>
          <button
            onClick={() => handleOpen(localUrl)}
            className="p-2 hover:bg-white/5 rounded-lg transition-colors"
            title={t('access.open')}
          >
            <IconExternalLink className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>
        <div className="flex items-center gap-2">
          <code className="flex-1 px-3 py-2 bg-black/20 rounded-lg text-xs font-mono text-indigo-400">{localUrl}</code>
          <button
            onClick={() => handleCopy(localUrl, 'local')}
            className="p-2 hover:bg-white/5 rounded-lg transition-colors"
            title={t('access.copy')}
          >
            {copied === 'local' ? (
              <IconCheck className="w-4 h-4 text-emerald-500" />
            ) : (
              <IconCopy className="w-4 h-4 text-muted-foreground" />
            )}
          </button>
        </div>
      </div>

      {showLocalIngress && (
        <div
          id="public-access"
          className="p-6 rounded-2xl bg-emerald-500/5 border border-emerald-500/25 space-y-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-2 text-sm font-bold text-foreground">
              <IconWifi className="w-4 h-4 text-emerald-400" />
              {t('access.lan.title')}
            </div>
            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide bg-emerald-500/20 text-emerald-400">
              {t('access.lan.recommended')}
            </span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">{t('access.lan.description')}</p>
          {remoteUrl ? (
            <>
              <div className="flex items-center gap-2">
                <code className="flex-1 min-w-0 px-3 py-2 bg-black/20 rounded-lg text-xs font-mono text-emerald-400 break-all">
                  {remoteUrl}
                </code>
                <button
                  type="button"
                  onClick={() => handleOpen(remoteUrl)}
                  className="p-2 hover:bg-white/5 rounded-lg transition-colors shrink-0"
                  title={t('access.open')}
                >
                  <IconExternalLink className="w-4 h-4 text-muted-foreground" />
                </button>
                <button
                  type="button"
                  onClick={() => handleCopy(remoteUrl, 'lan')}
                  className="p-2 hover:bg-white/5 rounded-lg transition-colors shrink-0"
                  title={t('access.copy')}
                >
                  {copied === 'lan' ? (
                    <IconCheck className="w-4 h-4 text-emerald-500" />
                  ) : (
                    <IconCopy className="w-4 h-4 text-muted-foreground" />
                  )}
                </button>
              </div>
              {lanQrSrc ? (
                <div className="hidden md:flex flex-col items-center gap-2 pt-2">
                  <div className="p-3 bg-white rounded-xl">
                    <img src={lanQrSrc} alt={t('access.lan.qrAlt')} width={160} height={160} className="block" />
                  </div>
                  <p className="text-xs text-muted-foreground">{t('access.lan.scanHint')}</p>
                </div>
              ) : null}
              {!isTauriRuntime() && (
                <p className="text-xs text-amber-500/80 leading-relaxed">{t('access.lan.webDevHint')}</p>
              )}
              {isTauriRuntime() && !config.enableRemoteAccess && (
                <p className="text-xs text-amber-500/80 leading-relaxed">{t('access.lan.tauriEnableRemote')}</p>
              )}
            </>
          ) : (
            <p className="text-xs text-muted-foreground">{t('access.fetchingIP')}</p>
          )}
        </div>
      )}

      {showLocalIngress && !config.requirePassword && isTauriRuntime() && config.enableRemoteAccess && (
        <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-start gap-3">
          <IconLock className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-amber-500/80 leading-relaxed">{t('access.securityWarning')}</p>
        </div>
      )}

      {showLocalIngress && (
        <IngressEntitlementGate>
          <div id="public-ingress" className="p-6 rounded-2xl bg-white/5 border border-white/10 space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-2 text-sm font-bold text-foreground">
                <IconGlobe className="w-4 h-4" />
                {t('access.ingress.title')}
              </div>
              {ingressRequired && (
                <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide bg-amber-500/20 text-amber-400">
                  {t('access.ingress.requiredBadge')}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">{t('access.ingress.description')}</p>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {t('access.ingress.docsHint')}{' '}
              <a
                href={docsTunnelUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline underline-offset-2 hover:text-primary/80"
              >
                {t('access.ingress.docsLink')}
              </a>
            </p>
            {!passwordProtectionEnabled && (
              <p className="text-xs text-amber-500/90">{t('access.ingress.passwordRequired')}</p>
            )}
            <div className="rounded-xl border border-white/10 bg-black/10 p-4 space-y-3">
              <p className="text-sm font-semibold text-foreground">{t('access.tunnel.title')}</p>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {localeIsZh ? t('access.tunnel.cnHint') : t('access.tunnel.globalHint')}
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void handleTunnelToggle()}
                  disabled={tunnelBusy || !passwordProtectionEnabled}
                  className="px-4 py-2 rounded-xl bg-indigo-500 hover:bg-indigo-600 disabled:opacity-50 text-white text-sm font-bold"
                >
                  {tunnelBusy
                    ? t('access.tunnel.starting')
                    : tunnelStatus?.state === 'running'
                      ? t('access.tunnel.stop')
                      : t('access.tunnel.start')}
                </button>
                <button
                  type="button"
                  onClick={() => void handleShareMobileLink()}
                  disabled={!passwordProtectionEnabled}
                  className="px-4 py-2 rounded-xl border border-white/15 text-sm font-medium hover:bg-white/5 disabled:opacity-50"
                >
                  {t('access.tunnel.shareMobile')}
                </button>
              </div>
              {tunnelStatus?.publicUrl ? (
                <div className="space-y-2">
                  <p className="text-xs text-emerald-400 break-all">{tunnelStatus.publicUrl}</p>
                  <span className="inline-flex items-center rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-emerald-300">
                    {t('access.tunnel.e2eeBadge')}
                  </span>
                  <p className="text-xs text-muted-foreground leading-relaxed">{t('access.tunnel.e2eeHint')}</p>
                </div>
              ) : null}
              {mobileHubQrSrc ? (
                <div className="flex flex-col items-center gap-2 pt-2">
                  <div className="p-3 bg-white rounded-xl">
                    <img
                      src={mobileHubQrSrc}
                      alt={t('access.tunnel.hubQrAlt')}
                      width={160}
                      height={160}
                      className="block"
                    />
                  </div>
                  <p className="text-xs text-muted-foreground text-center break-all">{mobileHubUrl}</p>
                  <p className="text-xs text-muted-foreground">{t('access.tunnel.hubScanHint')}</p>
                  {(isInstallable || isInstalled) ? (
                    <div className="w-full rounded-xl border border-border/60 bg-card/40 p-3 space-y-2 mt-2">
                      <p className="text-xs font-medium text-foreground">{t('access.tunnel.pwaTitle')}</p>
                      <p className="text-xs text-muted-foreground leading-relaxed">{t('access.tunnel.pwaHint')}</p>
                      {isInstalled ? (
                        <p className="text-xs text-emerald-400">{t('access.tunnel.pwaInstalled')}</p>
                      ) : (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="w-full sm:w-auto"
                          onClick={() => void promptInstall()}
                        >
                          {t('access.tunnel.pwaInstall')}
                        </Button>
                      )}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
              <input
                type="text"
                value={publicIngressBaseUrl || ''}
                onChange={(e) => setPublicIngressBaseUrl(e.target.value)}
                placeholder="https://..."
                className="flex-1 px-4 py-2.5 bg-black/20 border border-white/10 rounded-xl text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
              <button
                type="button"
                onClick={() => void handleTestIngress()}
                disabled={testingIngress}
                className="px-4 py-2.5 bg-indigo-500 hover:bg-indigo-600 disabled:opacity-50 text-white rounded-xl text-sm font-bold transition-colors whitespace-nowrap"
              >
                {testingIngress ? t('access.ingress.testing') : t('access.ingress.testButton')}
              </button>
            </div>
          </div>
        </IngressEntitlementGate>
      )}
    </div>
  );
});
AccessCard.displayName = 'AccessCard';
