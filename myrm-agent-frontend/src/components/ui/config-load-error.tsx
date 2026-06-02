'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from './button';
import { cn } from '@/lib/utils/classnameUtils';

interface ConfigLoadErrorProps {
  onRetry: () => void;
  className?: string;
}

const ConfigLoadError = memo(({ onRetry, className }: ConfigLoadErrorProps) => {
  const t = useTranslations('common.configLoadError');

  return (
    <div className={cn('flex flex-col items-center justify-center gap-4 py-16 px-6 text-center', className)}>
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
        <AlertCircle className="h-6 w-6 text-destructive" />
      </div>
      <div className="space-y-1.5">
        <p className="text-sm font-medium text-foreground">{t('title')}</p>
        <p className="text-xs text-muted-foreground max-w-[280px]">{t('description')}</p>
      </div>
      <Button variant="outline" size="sm" onClick={onRetry} className="gap-1.5">
        <RefreshCw className="h-3.5 w-3.5" />
        {t('retry')}
      </Button>
    </div>
  );
});

ConfigLoadError.displayName = 'ConfigLoadError';

export { ConfigLoadError };
