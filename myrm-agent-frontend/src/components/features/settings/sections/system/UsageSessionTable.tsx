'use client';

import { memo } from 'react';
import { IconChat } from '@/components/features/icons/PremiumIcons';
import { formatTokenCount, formatCost } from './RoutingAnalyticsPanel';
import { type SessionUsage } from '@/services/statistics';

export const SessionTable = memo<{
  sessions: SessionUsage[];
  t: ReturnType<typeof import('next-intl').useTranslations>;
  onSelectSession: (id: string) => void;
}>(({ sessions, t, onSelectSession }) => {
  if (sessions.length === 0) {
    return <div className="flex items-center justify-center h-20 text-sm text-muted-foreground">{t('noData')}</div>;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
        <IconChat className="w-4 h-4 text-primary" />
        {t('topSessions')}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border/50">
              <th className="text-left py-2 pr-3 text-muted-foreground font-medium">{t('session')}</th>
              <th className="text-right py-2 px-2 text-muted-foreground font-medium">{t('messages')}</th>
              <th className="text-right py-2 px-2 text-muted-foreground font-medium">{t('tokens')}</th>
              <th className="text-right py-2 pl-2 text-muted-foreground font-medium">{t('cost')}</th>
            </tr>
          </thead>
          <tbody>
            {sessions.slice(0, 10).map((s) => (
              <tr
                key={s.chatId}
                className="border-b border-border/30 last:border-0 cursor-pointer hover:bg-muted/50 transition-colors"
                onClick={() => onSelectSession(s.chatId)}
              >
                <td className="py-2 pr-3 max-w-[200px] truncate text-foreground" title={s.title}>
                  {s.title}
                </td>
                <td className="py-2 px-2 text-right tabular-nums text-muted-foreground">{s.messageCount}</td>
                <td className="py-2 px-2 text-right tabular-nums font-medium text-foreground">
                  {formatTokenCount(s.totalTokens)}
                </td>
                <td className="py-2 pl-2 text-right tabular-nums text-muted-foreground">
                  {s.costUsd > 0 ? formatCost(s.costUsd) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
});
SessionTable.displayName = 'SessionTable';
