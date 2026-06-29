'use client';

import { memo } from 'react';

export const PrivacyRoutePanel = memo<{
  breakdown: Record<string, number>;
  t: ReturnType<typeof import('next-intl').useTranslations>;
}>(({ breakdown, t }) => {
  const total = Object.values(breakdown).reduce((a, b) => a + b, 0);
  if (total === 0) return null;

  const localCount = breakdown['local'] ?? 0;
  const cloudCount = breakdown['cloud'] ?? 0;
  const localPct = Math.round((localCount / total) * 100);
  const cloudPct = 100 - localPct;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>{t('privacyRoutingDesc')}</span>
      </div>
      <div className="h-3 rounded-full overflow-hidden flex bg-muted">
        {localPct > 0 && (
          <div className="bg-green-500 dark:bg-green-400 transition-all" style={{ width: `${localPct}%` }} />
        )}
        {cloudPct > 0 && (
          <div className="bg-blue-500 dark:bg-blue-400 transition-all" style={{ width: `${cloudPct}%` }} />
        )}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="p-3 rounded-lg border border-border bg-background">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-2.5 h-2.5 rounded-full bg-green-500 dark:bg-green-400" />
            <span className="text-xs font-medium text-foreground">{t('privacyRouteLocal')}</span>
          </div>
          <div className="text-lg font-bold text-foreground">{localCount}</div>
          <div className="text-[10px] text-muted-foreground">{localPct}%</div>
        </div>
        <div className="p-3 rounded-lg border border-border bg-background">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-2.5 h-2.5 rounded-full bg-blue-500 dark:bg-blue-400" />
            <span className="text-xs font-medium text-foreground">{t('privacyRouteCloud')}</span>
          </div>
          <div className="text-lg font-bold text-foreground">{cloudCount}</div>
          <div className="text-[10px] text-muted-foreground">{cloudPct}%</div>
        </div>
      </div>
    </div>
  );
});
PrivacyRoutePanel.displayName = 'PrivacyRoutePanel';
