'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { fetchBackendHealth, type BackendHealthPayload } from '@/lib/backend-health';
import { cn } from '@/lib/utils/classnameUtils';

interface ConfigLoadErrorProps {
  onRetry: () => void;
  className?: string;
}

function formatHint(
  t: (key: string, values?: Record<string, string | number>) => string,
  health: BackendHealthPayload | null,
): string | null {
  if (health?.status === 'healthy' && health.listen_port != null) {
    const host = health.listen_host ?? '127.0.0.1';
    const proxy = health.frontend_proxy_port ?? health.listen_port;
    if (health.dev_mode === 'standalone_webui') {
      return t('hintStandalone', {
        host,
        port: health.listen_port,
        proxyPort: proxy,
      });
    }
    return t('hintSplitDev', {
      host,
      port: health.listen_port,
      proxyPort: proxy,
    });
  }
  return t('hintUnreachable');
}

const ConfigLoadError = memo(({ onRetry, className }: ConfigLoadErrorProps) => {
  const t = useTranslations('common.configLoadError');
  const [hint, setHint] = useState<string | null>(null);

  const loadHint = useCallback(async () => {
    const health = await fetchBackendHealth();
    setHint(formatHint(t, health));
  }, [t]);

  useEffect(() => {
    void loadHint();
  }, [loadHint]);

  const handleRetry = () => {
    void loadHint();
    onRetry();
  };

  return (
    <div className={cn('flex flex-col items-center justify-center gap-4 py-16 px-6 text-center', className)}>
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
        <AlertCircle className="h-6 w-6 text-destructive" />
      </div>
      <div className="space-y-1.5">
        <p className="text-sm font-medium text-foreground">{t('title')}</p>
        <p className="text-xs text-muted-foreground max-w-[320px]">{t('description')}</p>
        {hint ? (
          <p className="text-xs text-muted-foreground/90 max-w-[360px] whitespace-pre-line font-mono">
            {hint}
          </p>
        ) : null}
      </div>
      <Button variant="outline" size="sm" onClick={handleRetry} className="gap-1.5">
        <RefreshCw className="h-3.5 w-3.5" />
        {t('retry')}
      </Button>
    </div>
  );
});

ConfigLoadError.displayName = 'ConfigLoadError';

export { ConfigLoadError };
