"use client";

import { memo, useEffect, useState } from 'react';
import {
  IconChat,
  IconChart,
  IconChevronDown,
  IconChevronUp,
} from '@/components/features/icons/PremiumIcons';
import { formatTokenCount, formatCost } from './RoutingAnalyticsPanel';
import { getModelSessions, type UsageStats, type ModelSessionItem } from '@/services/statistics';

/* ─── ModelBreakdownItem ─── */

interface ModelBreakdownItemProps {
  model: string;
  data: { totalTokens: number; inputTokens: number; outputTokens: number; cachedTokens: number; costUsd: number; calls: number };
  totalTokens: number;
  t: ReturnType<typeof import('next-intl').useTranslations>;
  timeRange: number;
  onSelectSession: (id: string) => void;
}

const ModelBreakdownItem = memo<ModelBreakdownItemProps>(
  ({ model, data, totalTokens, t, timeRange, onSelectSession }) => {
    const [expanded, setExpanded] = useState(false);
    const [sessions, setSessions] = useState<ModelSessionItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const pct = totalTokens > 0 ? Math.round((data.totalTokens / totalTokens) * 100) : 0;
    const cacheRate = data.inputTokens > 0 ? Math.round((data.cachedTokens / data.inputTokens) * 100) : 0;

    useEffect(() => {
      if (!expanded) return;
      const fetchSessions = async () => {
        setLoading(true);
        setError(null);
        try {
          const list = await getModelSessions(model, timeRange);
          setSessions(list);
        } catch (err) {
          console.error('Failed to load sessions:', err);
          setError(t('retry'));
        } finally {
          setLoading(false);
        }
      };
      fetchSessions();
    }, [expanded, model, timeRange, t]);

    return (
      <div className="p-3 rounded-lg bg-background/40 border border-border/30 space-y-2 transition-all">
        <div
          className="flex items-center justify-between gap-2 cursor-pointer select-none group"
          onClick={() => setExpanded(!expanded)}
          role="button"
          tabIndex={0}
          title={expanded ? t('hideSessions') : t('showSessions')}
        >
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <div className="text-xs font-semibold text-foreground truncate group-hover:text-primary transition-colors">
                {model.split('/').pop()}
              </div>
              {expanded ? (
                <IconChevronUp className="w-3.5 h-3.5 text-muted-foreground/60" />
              ) : (
                <IconChevronDown className="w-3.5 h-3.5 text-muted-foreground/60 opacity-0 group-hover:opacity-100 transition-opacity" />
              )}
            </div>
            <div className="text-[10px] text-muted-foreground mt-0.5">
              {data.calls} {t('calls')} · {formatTokenCount(data.totalTokens)} tokens
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <div className="w-16 h-1.5 rounded-full bg-border/50 overflow-hidden">
              <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
            </div>
            <span className="text-[10px] tabular-nums text-muted-foreground w-8 text-right">{pct}%</span>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1 text-[10px] pt-1.5 border-t border-border/20">
          <div className="flex justify-between">
            <span className="text-muted-foreground">{t('inputTokens')}</span>
            <span className="tabular-nums text-foreground">{formatTokenCount(data.inputTokens)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">{t('outputTokens')}</span>
            <span className="tabular-nums text-foreground">{formatTokenCount(data.outputTokens)}</span>
          </div>
          {data.cachedTokens > 0 && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('cachedTokens')}</span>
              <span className="tabular-nums text-emerald-600 dark:text-emerald-400">
                {formatTokenCount(data.cachedTokens)} ({cacheRate}%)
              </span>
            </div>
          )}
          {data.costUsd > 0 && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('cost')}</span>
              <span className="tabular-nums text-foreground">{formatCost(data.costUsd)}</span>
            </div>
          )}
        </div>

        {expanded && (
          <div className="mt-3 pt-3 border-t border-border/20 space-y-2">
            <div className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground/80 flex items-center gap-1">
              <IconChat className="w-3 h-3 text-muted-foreground" />
              {t('sessionDrilldown')}
            </div>

            {loading ? (
              <div className="flex items-center justify-center py-4">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary" />
              </div>
            ) : error ? (
              <div className="flex items-center justify-between py-2 text-[10px] text-destructive">
                <span>{error}</span>
                <button onClick={() => setExpanded(false)} className="text-xs text-primary hover:underline">
                  {t('retry')}
                </button>
              </div>
            ) : sessions.length === 0 ? (
              <div className="text-[10px] text-muted-foreground/60 py-2 italic text-center">{t('noModelSessions')}</div>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-border/25 bg-muted/15">
                <table className="w-full text-[10px] text-left">
                  <thead>
                    <tr className="border-b border-border/20 bg-muted/20 text-muted-foreground font-medium">
                      <th className="py-1.5 px-2 text-left">{t('session')}</th>
                      <th className="py-1.5 px-1.5 text-center">{t('messages')}</th>
                      <th className="py-1.5 px-1.5 text-right">{t('tokens')}</th>
                      <th className="py-1.5 px-2 text-right">{t('cost')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sessions.map((item) => (
                      <tr
                        key={item.chatId}
                        className="border-b border-border/10 last:border-0 hover:bg-muted/30 cursor-pointer transition-colors"
                        onClick={() => onSelectSession(item.chatId)}
                      >
                        <td className="py-2 px-2 max-w-[120px] sm:max-w-[180px] truncate">
                          <div className="font-medium text-foreground truncate">{item.title}</div>
                          <div className="text-[8px] text-muted-foreground/60 mt-0.5 flex items-center gap-1">
                            <span className="capitalize">{item.actionMode}</span>
                            <span>·</span>
                            <span>{item.lastUsedAt ? new Date(item.lastUsedAt).toLocaleDateString() : ''}</span>
                          </div>
                        </td>
                        <td className="py-2 px-1.5 text-center tabular-nums text-muted-foreground">{item.calls}</td>
                        <td className="py-2 px-1.5 text-right tabular-nums text-muted-foreground">
                          <div>{formatTokenCount(item.totalTokens)}</div>
                          <div className="text-[8px] text-muted-foreground/40 mt-0.5">
                            I {formatTokenCount(item.inputTokens)} / O {formatTokenCount(item.outputTokens)}
                          </div>
                        </td>
                        <td className="py-2 px-2 text-right tabular-nums text-foreground font-medium">
                          {formatCost(item.costUsd)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    );
  },
);
ModelBreakdownItem.displayName = 'ModelBreakdownItem';

/* ─── ModelBreakdown ─── */

interface ModelBreakdownProps {
  stats: UsageStats;
  t: ReturnType<typeof import('next-intl').useTranslations>;
  timeRange: number;
  onSelectSession: (id: string) => void;
}

export const ModelBreakdown = memo<ModelBreakdownProps>(({ stats, t, timeRange, onSelectSession }) => {
  const models = Object.entries(stats.modelBreakdown);
  if (models.length === 0) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
        <IconChart className="w-4 h-4 text-primary" />
        {t('modelBreakdown')}
      </div>
      <div className="grid gap-2">
        {models.map(([model, data]) => (
          <ModelBreakdownItem
            key={model}
            model={model}
            data={data as ModelBreakdownItemProps['data']}
            totalTokens={stats.totalTokens}
            t={t}
            timeRange={timeRange}
            onSelectSession={onSelectSession}
          />
        ))}
      </div>
    </div>
  );
});
ModelBreakdown.displayName = 'ModelBreakdown';


export type { ModelBreakdownItemProps };
