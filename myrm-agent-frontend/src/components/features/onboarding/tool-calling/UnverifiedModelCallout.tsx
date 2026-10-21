'use client';

import React, { memo } from 'react';
import { useTranslations } from 'next-intl';
import { AlertTriangle, Info } from 'lucide-react';
import { isVerifiedToolCallingModel } from './verifiedToolModels';

interface UnverifiedModelCalloutProps {
  modelName: string;
  className?: string;
}

export const UnverifiedModelCallout = memo<UnverifiedModelCalloutProps>(({ modelName, className = '' }) => {
  const t = useTranslations('chat.localCapabilities');

  if (!modelName || !modelName.trim()) {
    return null;
  }

  const isVerified = isVerifiedToolCallingModel(modelName);

  if (isVerified) {
    return (
      <div
        data-testid="callout-verified"
        className={`flex items-start gap-2.5 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs text-emerald-800 dark:text-emerald-300 transition-colors ${className}`}
      >
        <Info className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400 mt-0.5" />
        <div className="space-y-0.5">
          <span className="font-medium">{t('verifiedBadge', { model: modelName })}</span>
          <p className="text-muted-foreground dark:text-emerald-400/80 text-[11px]">{t('verifiedDescription')}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid="callout-unverified"
      className={`flex items-start gap-2.5 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-900 dark:text-amber-200 transition-colors ${className}`}
    >
      <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
      <div className="space-y-0.5">
        <span className="font-medium">{t('unverifiedWarningTitle', { model: modelName })}</span>
        <p className="text-muted-foreground dark:text-amber-300/80 text-[11px]">{t('unverifiedWarningDescription')}</p>
      </div>
    </div>
  );
});

UnverifiedModelCallout.displayName = 'UnverifiedModelCallout';
