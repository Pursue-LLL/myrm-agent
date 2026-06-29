'use client';

import { useCallback, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Copy, Eye, EyeOff, Terminal } from 'lucide-react';
import { toast } from 'sonner';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { useIngressUrl } from '@/hooks/useIngressUrl';

export function isValidCronTriggerRegex(pattern: string): boolean {
  if (!pattern) return true;
  try {
    new RegExp(pattern);
    return true;
  } catch {
    return false;
  }
}

function buildCurlExample(url: string, secret?: string | null): string {
  const secretHeader = secret ? `\n  -H "x-webhook-secret: ${secret}" \\` : '';
  return `curl -X POST "${url}" \\${secretHeader}\n  -H "Content-Type: application/json" \\\n  -d '{"event": "test"}'`;
}

export function CronTriggerWebhookDisplay({ path, secret }: { path?: string | null; secret?: string | null }) {
  const t = useTranslations('cron');
  const [showSecret, setShowSecret] = useState(false);
  const [showCurl, setShowCurl] = useState(false);

  const { url: webhookUrl, loading } = useIngressUrl(`/api/v1/cron/triggers/webhook/${path || ''}`);
  const isLocalhost = webhookUrl.includes('localhost') || webhookUrl.includes('127.0.0.1');

  const copyToClipboard = useCallback((text: string) => {
    writeToClipboard(text);
    toast.success('Copied');
  }, []);

  if (!path) return null;

  const curlCmd = buildCurlExample(webhookUrl, secret);

  return (
    <div className="rounded border bg-muted/30 px-2 py-1.5 space-y-1">
      <div className="flex items-center gap-1.5 text-xs">
        <span className="text-muted-foreground shrink-0">{t('triggerWebhookUrl')}:</span>
        {loading ? (
          <div className="h-4 flex-1 bg-muted/50 rounded animate-pulse" />
        ) : (
          <code className="text-[10px] font-mono truncate flex-1">{webhookUrl}</code>
        )}
        <button
          onClick={() => copyToClipboard(webhookUrl)}
          disabled={loading}
          className="shrink-0 text-muted-foreground hover:text-foreground disabled:opacity-50"
        >
          <Copy className="h-3 w-3" />
        </button>
      </div>
      {!loading && isLocalhost && (
        <div className="text-[10px] text-amber-500 italic mt-0.5 leading-relaxed">
          {t('triggerLocalhostWarning')}{' '}
          <Link href="/settings/system#public-ingress" className="underline font-medium not-italic hover:text-amber-400">
            {t('triggerOpenSystemSettings')}
          </Link>
        </div>
      )}
      {secret && (
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-muted-foreground shrink-0">{t('triggerWebhookSecret')}:</span>
          <code className="text-[10px] font-mono truncate flex-1">{showSecret ? secret : '••••••••••••'}</code>
          <button
            onClick={() => setShowSecret(!showSecret)}
            className="shrink-0 text-muted-foreground hover:text-foreground"
          >
            {showSecret ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
          </button>
          <button
            onClick={() => copyToClipboard(secret)}
            className="shrink-0 text-muted-foreground hover:text-foreground"
          >
            <Copy className="h-3 w-3" />
          </button>
        </div>
      )}
      <div className="flex items-center gap-1.5 text-xs">
        <button
          onClick={() => setShowCurl(!showCurl)}
          className="flex items-center gap-1 text-muted-foreground hover:text-foreground"
        >
          <Terminal className="h-3 w-3" />
          <span className="text-[10px]">{t('triggerWebhookCurl')}</span>
        </button>
      </div>
      {showCurl && (
        <div className="relative rounded bg-background/80 p-1.5">
          <pre className="text-[10px] font-mono whitespace-pre-wrap break-all text-foreground/80">{curlCmd}</pre>
          <button
            onClick={() => copyToClipboard(curlCmd)}
            className="absolute top-1 right-1 text-muted-foreground hover:text-foreground"
          >
            <Copy className="h-3 w-3" />
          </button>
        </div>
      )}
    </div>
  );
}
