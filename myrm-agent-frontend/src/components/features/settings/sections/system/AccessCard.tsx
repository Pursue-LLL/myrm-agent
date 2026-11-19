'use client';

import { memo, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
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
import { useIngressRequirement } from '@/hooks/billing/useIngressRequirement';
import { isLocalMode, isTauriRuntime } from '@/lib/deploy-mode';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { toast } from '@/lib/utils/toast';
import { systemService } from '@/services/system';
import { TailscaleAccessCard } from './TailscaleAccessCard';
import { PublicIngressCard } from './PublicIngressCard';
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
  const [copied, setCopied] = useState<string | null>(null);
  const [lanNetworkUrl, setLanNetworkUrl] = useState('');

  const accessEnabled = config.enableWebUIMode || (!isTauriRuntime() && isLocalMode());
  const webuiPort = resolveWebuiPort(config);
  const showLocalIngress = isLocalMode();
  const ingressResolved = ingressSnapshot !== null;
  const ingressRequired = ingressResolved && ingressSnapshot.required;

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

  if (!accessEnabled) {
    return (
      <div className="p-6 rounded-2xl bg-card border border-border text-center text-muted-foreground">
        <IconWifiOff className="w-8 h-8 mx-auto mb-3 opacity-30" />
        <p className="text-sm">{t('access.disabled')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {showLocalIngress && (
        <div className="p-4 rounded-xl bg-indigo-500/10 border border-indigo-500/20 space-y-2">
          <p className="text-sm font-bold text-indigo-600 dark:text-indigo-300">{t('access.guide.title')}</p>
          <p className="text-xs text-muted-foreground leading-relaxed">{t('access.guide.lanFirst')}</p>
          {ingressResolved &&
            (ingressRequired ? (
              <p className="text-xs text-muted-foreground leading-relaxed">{t('access.guide.publicIngressRequired')}</p>
            ) : (
              <p className="text-xs text-muted-foreground leading-relaxed">{t('access.guide.publicIngressOptional')}</p>
            ))}
        </div>
      )}

      <div className="p-6 rounded-2xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-bold text-foreground">
            <IconGlobe className="w-4 h-4" />
            {t('access.local')}
          </div>
          <button
            onClick={() => handleOpen(localUrl)}
            className="p-2 hover:bg-muted dark:hover:bg-white/5 rounded-lg transition-colors"
            title={t('access.open')}
          >
            <IconExternalLink className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>
        <div className="flex items-center gap-2">
          <code className="flex-1 px-3 py-2 bg-muted/50 dark:bg-black/20 rounded-lg text-xs font-mono text-indigo-600 dark:text-indigo-400">
            {localUrl}
          </code>
          <button
            onClick={() => handleCopy(localUrl, 'local')}
            className="p-2 hover:bg-muted dark:hover:bg-white/5 rounded-lg transition-colors"
            title={t('access.copy')}
          >
            {copied === 'local' ? (
              <IconCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-500" />
            ) : (
              <IconCopy className="w-4 h-4 text-muted-foreground" />
            )}
          </button>
        </div>
      </div>

      {showLocalIngress && (
        <div id="public-access" className="p-6 rounded-2xl bg-emerald-500/5 border border-emerald-500/25 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-2 text-sm font-bold text-foreground">
              <IconWifi className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
              {t('access.lan.title')}
            </div>
            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide bg-emerald-500/20 text-emerald-800 dark:text-emerald-400">
              {t('access.lan.recommended')}
            </span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">{t('access.lan.description')}</p>
          {remoteUrl ? (
            <>
              <div className="flex items-center gap-2">
                <code className="flex-1 min-w-0 px-3 py-2 bg-muted/50 dark:bg-black/20 rounded-lg text-xs font-mono text-emerald-700 dark:text-emerald-400 break-all">
                  {remoteUrl}
                </code>
                <button
                  type="button"
                  onClick={() => handleOpen(remoteUrl)}
                  className="p-2 hover:bg-muted dark:hover:bg-white/5 rounded-lg transition-colors shrink-0"
                  title={t('access.open')}
                >
                  <IconExternalLink className="w-4 h-4 text-muted-foreground" />
                </button>
                <button
                  type="button"
                  onClick={() => handleCopy(remoteUrl, 'lan')}
                  className="p-2 hover:bg-muted dark:hover:bg-white/5 rounded-lg transition-colors shrink-0"
                  title={t('access.copy')}
                >
                  {copied === 'lan' ? (
                    <IconCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-500" />
                  ) : (
                    <IconCopy className="w-4 h-4 text-muted-foreground" />
                  )}
                </button>
              </div>
              {lanQrSrc ? (
                <div className="hidden md:flex flex-col items-center gap-2 pt-2">
                  <div className="p-3 bg-white rounded-xl">
                    {/* oxlint-disable-next-line next/no-img-element -- the QR code is rendered per request by the backend, so next/image has nothing to optimize */}
                    <img src={lanQrSrc} alt={t('access.lan.qrAlt')} width={160} height={160} className="block" />
                  </div>
                  <p className="text-xs text-muted-foreground">{t('access.lan.scanHint')}</p>
                </div>
              ) : null}
              {!isTauriRuntime() && (
                <p className="text-xs text-amber-700 dark:text-amber-500/80 leading-relaxed">
                  {t('access.lan.webDevHint')}
                </p>
              )}
              {isTauriRuntime() && !config.enableRemoteAccess && (
                <p className="text-xs text-amber-700 dark:text-amber-500/80 leading-relaxed">
                  {t('access.lan.tauriEnableRemote')}
                </p>
              )}
            </>
          ) : (
            <p className="text-xs text-muted-foreground">{t('access.fetchingIP')}</p>
          )}
        </div>
      )}

      {showLocalIngress && <TailscaleAccessCard webuiPort={webuiPort} />}

      {showLocalIngress && !config.requirePassword && isTauriRuntime() && config.enableRemoteAccess && (
        <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-start gap-3">
          <IconLock className="w-4 h-4 text-amber-700 dark:text-amber-500 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-amber-700 dark:text-amber-500/80 leading-relaxed">{t('access.securityWarning')}</p>
        </div>
      )}

      {showLocalIngress && (
        <IngressEntitlementGate>
          <PublicIngressCard
            webuiPort={webuiPort}
            requirePassword={config.requirePassword}
            ingressRequired={ingressRequired}
          />
        </IngressEntitlementGate>
      )}
    </div>
  );
});
AccessCard.displayName = 'AccessCard';
