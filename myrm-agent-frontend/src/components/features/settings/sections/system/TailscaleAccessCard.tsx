'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconCheck,
  IconCopy,
  IconExternalLink,
  IconRefresh,
  IconShield,
  IconWifi,
} from '@/components/features/icons/PremiumIcons';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { toast } from '@/lib/utils/toast';
import { remoteAccessService, type TailscaleStatus } from '@/services/remoteAccess';

interface TailscaleAccessCardProps {
  webuiPort: number;
}

export const TailscaleAccessCard = memo<TailscaleAccessCardProps>(({ webuiPort }) => {
  const t = useTranslations('settings.system.access');
  const [status, setStatus] = useState<TailscaleStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    try {
      const data = await remoteAccessService.getTailscaleStatus();
      setStatus(data);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus]);

  const handleCopy = (text: string, type: string) => {
    writeToClipboard(text);
    setCopied(type);
    toast.success(t('copied'));
    setTimeout(() => setCopied(null), 2000);
  };

  const handleOpen = (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const primaryIp = status?.ips && status.ips.length > 0 ? status.ips[0] : null;
  const directIpUrl = primaryIp ? `http://${primaryIp}:${webuiPort}` : null;
  const magicDnsUrl = status?.fqdn ? `http://${status.fqdn}:${webuiPort}` : null;
  const preferredUrl = status?.serveUrl || magicDnsUrl || directIpUrl;

  const qrSrc = preferredUrl
    ? `/webui/qrcode.png?url=${encodeURIComponent(preferredUrl)}`
    : '';

  return (
    <div className="p-6 rounded-2xl bg-cyan-500/5 border border-cyan-500/20 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 text-sm font-bold text-foreground">
            <IconShield className="w-4 h-4 text-cyan-400" />
            {t('tailscale.title')}
          </div>
          <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide bg-cyan-500/20 text-cyan-400">
            {t('tailscale.badge')}
          </span>
        </div>
        <button
          type="button"
          onClick={() => void fetchStatus()}
          disabled={loading}
          className="p-1.5 hover:bg-white/5 rounded-lg transition-colors text-muted-foreground hover:text-foreground disabled:opacity-50"
          title="Refresh Tailscale status"
        >
          <IconRefresh className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <p className="text-xs text-muted-foreground leading-relaxed">
        {t('tailscale.description')}
      </p>

      {status?.running ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-300">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              {t('tailscale.statusActive')}
            </span>
            {status.nodeName && (
              <span className="text-xs text-muted-foreground">
                ({status.nodeName}{status.tailnet ? ` @ ${status.tailnet}` : ''})
              </span>
            )}
          </div>

          {preferredUrl && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <code className="flex-1 min-w-0 px-3 py-2 bg-black/20 rounded-lg text-xs font-mono text-cyan-400 break-all">
                  {preferredUrl}
                </code>
                <button
                  type="button"
                  onClick={() => handleOpen(preferredUrl)}
                  className="p-2 hover:bg-white/5 rounded-lg transition-colors shrink-0"
                  title={t('open')}
                >
                  <IconExternalLink className="w-4 h-4 text-muted-foreground" />
                </button>
                <button
                  type="button"
                  onClick={() => handleCopy(preferredUrl, 'tailscale-url')}
                  className="p-2 hover:bg-white/5 rounded-lg transition-colors shrink-0"
                  title={t('copy')}
                >
                  {copied === 'tailscale-url' ? (
                    <IconCheck className="w-4 h-4 text-emerald-500" />
                  ) : (
                    <IconCopy className="w-4 h-4 text-muted-foreground" />
                  )}
                </button>
              </div>

              {qrSrc && (
                <div className="hidden md:flex flex-col items-center gap-2 pt-2">
                  <div className="p-3 bg-white rounded-xl">
                    <img
                      src={qrSrc}
                      alt={t('tailscale.qrAlt')}
                      width={160}
                      height={160}
                      className="block"
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">{t('tailscale.scanHint')}</p>
                </div>
              )}
            </div>
          )}

          <div className="rounded-xl border border-white/10 bg-black/10 p-3 space-y-1.5 text-xs">
            {primaryIp && (
              <div className="flex justify-between items-center text-muted-foreground">
                <span>{t('tailscale.ipLabel')}:</span>
                <span className="font-mono text-foreground">{primaryIp}</span>
              </div>
            )}
            {status.fqdn && (
              <div className="flex justify-between items-center text-muted-foreground">
                <span>{t('tailscale.magicDnsLabel')}:</span>
                <span className="font-mono text-foreground">{status.fqdn}</span>
              </div>
            )}
            {status.user && (
              <div className="flex justify-between items-center text-muted-foreground">
                <span>{t('tailscale.userLabel')}:</span>
                <span className="font-mono text-foreground">{status.user}</span>
              </div>
            )}
          </div>

          <div className="p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-xs text-cyan-300 leading-relaxed">
            {t('tailscale.serveHint').replace('{port}', String(webuiPort))}
          </div>
        </div>
      ) : status?.installed ? (
        <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-amber-300">
            <IconWifi className="w-4 h-4 text-amber-400 shrink-0" />
            <span>{t('tailscale.statusInactive')}</span>
          </div>
        </div>
      ) : (
        <div className="p-4 rounded-xl bg-white/5 border border-white/10 flex items-center justify-between gap-3">
          <span className="text-xs text-muted-foreground">{t('tailscale.statusNotInstalled')}</span>
          <a
            href="https://tailscale.com/download"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-primary underline underline-offset-2 hover:text-primary/80"
          >
            {t('tailscale.learnMore')}
          </a>
        </div>
      )}
    </div>
  );
});

TailscaleAccessCard.displayName = 'TailscaleAccessCard';
