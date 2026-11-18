'use client';

import { memo, useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { IconGlobe } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { usePWAInstall } from '@/hooks/pwa/usePWAInstall';
import { getDocsUrl, isTauriRuntime } from '@/lib/deploy-mode';
import { computeE2EEFingerprintFromB64 } from '@/lib/e2ee/fingerprint';
import { buildMobileHubUrl } from '@/lib/mobileRemote';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { toast } from '@/lib/utils/toast';
import { isValidPublicIngressBaseUrl } from '@/lib/utils/urlUtils';
import { remoteAccessService, type TunnelStatus } from '@/services/remoteAccess';
import { systemService } from '@/services/system';
import { fetchWebuiProtection } from '@/services/webui-auth';
import useConfigStore from '@/store/useConfigStore';

/** Cipher suite of the remote-access handshake; a protocol identifier, shown the same in every language. */
const E2EE_ALGORITHM = 'NaCl Box (Curve25519)';

interface PublicIngressCardProps {
  webuiPort: number;
  /** Stored password setting; in a browser the server's live answer takes precedence. */
  requirePassword: boolean;
  ingressRequired: boolean;
}

export const PublicIngressCard = memo<PublicIngressCardProps>(({ webuiPort, requirePassword, ingressRequired }) => {
  const t = useTranslations('settings.system');
  const locale = useLocale();
  const publicIngressBaseUrl = useConfigStore((s) => s.publicIngressBaseUrl);
  const setPublicIngressBaseUrl = useConfigStore((s) => s.setPublicIngressBaseUrl);
  const { isInstallable, isInstalled, promptInstall } = usePWAInstall();
  const [testingIngress, setTestingIngress] = useState(false);
  const [serverRequirePassword, setServerRequirePassword] = useState<boolean | null>(null);
  const [tunnelStatus, setTunnelStatus] = useState<TunnelStatus | null>(null);
  const [tunnelBusy, setTunnelBusy] = useState(false);
  const [mobileHubUrl, setMobileHubUrl] = useState('');
  const [e2eePublicKeyB64, setE2eePublicKeyB64] = useState<string | null>(null);
  const localeIsZh = locale.startsWith('zh');
  const passwordProtectionEnabled = isTauriRuntime() ? requirePassword : (serverRequirePassword ?? requirePassword);
  const docsTunnelUrl = getDocsUrl('/guides/tunnel');
  const mobileHubQrSrc = mobileHubUrl ? `/webui/qrcode.png?url=${encodeURIComponent(mobileHubUrl)}` : '';

  useEffect(() => {
    if (isTauriRuntime()) {
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
  }, []);

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
    let cancelled = false;
    void remoteAccessService.getTunnelStatus().then((status) => {
      if (!cancelled) {
        setTunnelStatus(status);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

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
      if (e2eeKey?.publicKeyB64) {
        setE2eePublicKeyB64(e2eeKey.publicKeyB64);
      }
      writeToClipboard(hubUrl);
      toast.success(t('access.tunnel.shareCopied'));
    } catch {
      toast.error(t('access.tunnel.error'));
    }
  };

  useEffect(() => {
    if (!passwordProtectionEnabled || tunnelStatus?.state !== 'running' || mobileHubUrl) {
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
      if (serverKey) {
        setE2eePublicKeyB64(serverKey);
      }
      setMobileHubUrl(
        buildMobileHubUrl(mobilePath, tunnelStatus.publicUrl ?? '', publicIngressBaseUrl ?? '', serverKey),
      );
    });
    return () => {
      cancelled = true;
    };
  }, [passwordProtectionEnabled, tunnelStatus?.state, tunnelStatus?.publicUrl, publicIngressBaseUrl, mobileHubUrl]);

  return (
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
            {e2eePublicKeyB64 && (
              <dl className="mt-1 space-y-1 text-[11px]">
                <div className="flex gap-2">
                  <dt className="text-muted-foreground shrink-0">{t('access.tunnel.e2eeAlgorithm')}</dt>
                  <dd className="font-mono text-emerald-300">{E2EE_ALGORITHM}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="text-muted-foreground shrink-0">{t('access.tunnel.e2eeFingerprint')}</dt>
                  <dd className="font-mono tracking-wider text-emerald-300">
                    {computeE2EEFingerprintFromB64(e2eePublicKeyB64)}
                  </dd>
                </div>
              </dl>
            )}
          </div>
        ) : null}
        {mobileHubQrSrc ? (
          <div className="flex flex-col items-center gap-2 pt-2">
            <div className="p-3 bg-white rounded-xl">
              {/* oxlint-disable-next-line next/no-img-element -- the QR code is rendered per request by the backend, so next/image has nothing to optimize */}
              <img src={mobileHubQrSrc} alt={t('access.tunnel.hubQrAlt')} width={160} height={160} className="block" />
            </div>
            <p className="text-xs text-muted-foreground text-center break-all">{mobileHubUrl}</p>
            <p className="text-xs text-muted-foreground">{t('access.tunnel.hubScanHint')}</p>
            {isInstallable || isInstalled ? (
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
  );
});
PublicIngressCard.displayName = 'PublicIngressCard';
