'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconCopy, IconCheck } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { isSandbox } from '@/lib/deploy-mode';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { getCpChannelCredentialStatus } from '@/services/channels';

interface CpInboundUrlBannerProps {
  channel: 'slack' | 'discord' | 'telegram';
}

export function CpInboundUrlBanner({ channel }: CpInboundUrlBannerProps) {
  const t = useTranslations('channels');
  const [url, setUrl] = useState('');
  const [copied, setCopied] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (!isSandbox()) return;
    const handler = () => setRefreshKey((k) => k + 1);
    window.addEventListener('channel-credentials-saved', handler);
    return () => window.removeEventListener('channel-credentials-saved', handler);
  }, []);

  useEffect(() => {
    if (!isSandbox()) return;
    let cancelled = false;
    void (async () => {
      try {
        const status = await getCpChannelCredentialStatus();
        if (cancelled) return;
        setUrl(status.webhook_urls[channel] ?? '');
      } catch {
        if (!cancelled) setUrl('');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [channel, refreshKey]);

  const handleCopy = useCallback(async () => {
    if (!url) return;
    await writeToClipboard(url);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }, [url]);

  if (!isSandbox() || !url) return null;

  const label = channel === 'discord' ? t('cpInteractionsUrlLabel') : t('cpWebhookUrlLabel');

  return (
    <div className="rounded-lg border border-primary/20 bg-primary/5 px-3 py-3 space-y-2">
      <p className="text-xs font-medium text-foreground">{label}</p>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <code className="flex-1 break-all rounded-md bg-background/80 px-2 py-1.5 text-xs text-muted-foreground border border-border/60">
          {url}
        </code>
        <Button type="button" variant="outline" size="sm" className="shrink-0" onClick={handleCopy}>
          {copied ? (
            <IconCheck className="mr-1.5 h-3.5 w-3.5 text-green-500" />
          ) : (
            <IconCopy className="mr-1.5 h-3.5 w-3.5" />
          )}
          {copied ? t('cpUrlCopied') : t('cpUrlCopy')}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">{t('cpWebhookHint')}</p>
    </div>
  );
}
