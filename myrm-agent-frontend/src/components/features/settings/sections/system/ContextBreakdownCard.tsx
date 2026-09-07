'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { type ContextBreakdown } from '@/services/statistics';
import { formatTokenCount } from './RoutingAnalyticsPanel';
import { cn } from '@/lib/utils/classnameUtils';

interface ContextBreakdownCardProps {
  breakdown?: ContextBreakdown;
}

const ContextBreakdownCard = memo<ContextBreakdownCardProps>(({ breakdown }) => {
  const t = useTranslations('settings.sessionAnalytics.contextDoctor');

  if (!breakdown) {
    return null;
  }

  const total = breakdown.total_context_tokens || 1;
  const sysPct = Math.round((breakdown.system_tokens / total) * 100);
  const chatPct = Math.round((breakdown.chat_tokens / total) * 100);
  const toolPct = Math.round((breakdown.tool_tokens / total) * 100);
  const filePct = Math.max(0, 100 - sysPct - chatPct - toolPct);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20';
      case 'critical':
        return 'text-rose-500 bg-rose-500/10 border-rose-500/20';
      default:
        return 'text-amber-500 bg-amber-500/10 border-amber-500/20';
    }
  };

  return (
    <div className="space-y-4 p-4 rounded-xl border border-border/50 bg-background/50 backdrop-blur-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-primary" />
          <h3 className="text-sm font-semibold text-foreground">{t('title')}</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">{t('healthScore')}:</span>
          <span
            className={cn(
              'px-2 py-0.5 rounded text-xs font-semibold tabular-nums border',
              getStatusColor(breakdown.diagnosis_status)
            )}
          >
            {breakdown.health_score}/100
          </span>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">{breakdown.diagnosis_message}</p>

      {/* Four-color multi-segmented distribution bar */}
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs font-medium text-muted-foreground">
          <span>{t('composition')}</span>
          <span className="tabular-nums font-semibold text-foreground">
            {formatTokenCount(breakdown.total_context_tokens)} Tokens
          </span>
        </div>
        <div className="h-2.5 w-full flex rounded-full overflow-hidden bg-muted/40">
          <div
            style={{ width: `${sysPct}%` }}
            className="bg-indigo-500 transition-all duration-300"
            title={`${t('system')}: ${sysPct}%`}
          />
          <div
            style={{ width: `${chatPct}%` }}
            className="bg-sky-500 transition-all duration-300"
            title={`${t('chat')}: ${chatPct}%`}
          />
          <div
            style={{ width: `${toolPct}%` }}
            className="bg-amber-500 transition-all duration-300"
            title={`${t('tools')}: ${toolPct}%`}
          />
          <div
            style={{ width: `${filePct}%` }}
            className="bg-emerald-500 transition-all duration-300"
            title={`${t('files')}: ${filePct}%`}
          />
        </div>

        {/* Legend */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 text-xs">
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-indigo-500" />
            <span className="text-muted-foreground">{t('system')}:</span>
            <span className="font-semibold tabular-nums">{formatTokenCount(breakdown.system_tokens)}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-sky-500" />
            <span className="text-muted-foreground">{t('chat')}:</span>
            <span className="font-semibold tabular-nums">{formatTokenCount(breakdown.chat_tokens)}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-amber-500" />
            <span className="text-muted-foreground">{t('tools')}:</span>
            <span className="font-semibold tabular-nums">{formatTokenCount(breakdown.tool_tokens)}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-emerald-500" />
            <span className="text-muted-foreground">{t('files')}:</span>
            <span className="font-semibold tabular-nums">{formatTokenCount(breakdown.file_tokens)}</span>
          </div>
        </div>
      </div>

      {/* Top Hotspots */}
      {breakdown.hotspots && breakdown.hotspots.length > 0 && (
        <div className="space-y-2 pt-2 border-t border-border/40">
          <div className="text-xs font-semibold text-foreground flex items-center justify-between">
            <span>{t('hotspotsTitle')}</span>
            <span className="text-[10px] text-muted-foreground font-normal">{t('hotspotsSubtitle')}</span>
          </div>
          <div className="space-y-1.5">
            {breakdown.hotspots.map((h, i) => (
              <div
                key={i}
                className="flex items-center justify-between p-2 rounded-lg bg-background/80 border border-border/40 text-xs"
              >
                <div className="flex items-center gap-2 truncate">
                  <span className="font-mono text-[11px] text-foreground font-medium truncate">
                    #{h.step_sequence} {h.tool_name}
                  </span>
                  {h.status === 'auto_pruned' && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                      {t('autoPruned')}
                    </span>
                  )}
                  {h.status === 'error' && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-rose-500/10 text-rose-500 border border-rose-500/20">
                      {t('error')}
                    </span>
                  )}
                </div>
                <span className="tabular-nums font-semibold text-muted-foreground shrink-0 ml-2">
                  ~{formatTokenCount(h.tokens)} Tok
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
});

ContextBreakdownCard.displayName = 'ContextBreakdownCard';

export default ContextBreakdownCard;
