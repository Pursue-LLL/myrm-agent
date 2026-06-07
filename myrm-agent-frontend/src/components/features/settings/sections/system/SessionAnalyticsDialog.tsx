'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconX, IconClock, IconChat, IconChart, IconZap, IconAlertCircle } from '@/components/features/icons/PremiumIcons';
import { getSessionAnalytics, type SessionAnalytics } from '@/services/statistics';
import { formatCost, formatTokenCount } from './RoutingAnalyticsPanel';
import { cn } from '@/lib/utils/classnameUtils';
import SessionContextHealthPanel from './SessionContextHealthPanel';
import ExecutionTraceTimeline from './ExecutionTraceTimeline';

interface SessionAnalyticsDialogProps {
  sessionId: string;
  onClose: () => void;
}

const SessionAnalyticsDialog = memo<SessionAnalyticsDialogProps>(({ sessionId, onClose }) => {
  const t = useTranslations('settings.sessionAnalytics');
  const [data, setData] = useState<SessionAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        setError(null);
        const result = await getSessionAnalytics(sessionId, true);
        setData(result);
      } catch (err) {
        if (err instanceof Error) {
          const message = err.message.toLowerCase();
          if (message.includes('not found') || message.includes('404')) {
            setError('Session not found or has been deleted');
          } else if (message.includes('access denied') || message.includes('403') || message.includes('forbidden')) {
            setError('Access denied: You do not have permission to view this session');
          } else if (message.includes('500') || message.includes('internal')) {
            setError('Server error: Please try again later');
          } else {
            setError(err.message);
          }
        } else {
          setError('Failed to load session analytics');
        }
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [sessionId]);

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) {
        onClose();
      }
    },
    [onClose],
  );

  if (loading) {
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
        onClick={handleBackdropClick}
      >
        <div className="bg-background border border-border rounded-lg p-8 max-w-4xl w-full mx-4">
          <div className="flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
        onClick={handleBackdropClick}
      >
        <div className="bg-background border border-border rounded-lg p-8 max-w-4xl w-full mx-4">
          <div className="flex items-center gap-2 text-destructive">
            <IconAlertCircle className="w-5 h-5" />
            <span>{error || 'Session not found'}</span>
          </div>
          <button
            onClick={onClose}
            className="mt-4 px-4 py-2 bg-primary text-primary-foreground rounded-full hover:bg-primary/90"
          >
            {t('close')}
          </button>
        </div>
      </div>
    );
  }

  const durationSeconds = Math.round(data.duration_ms / 1000);
  const durationText =
    durationSeconds >= 60 ? `${Math.floor(durationSeconds / 60)}m ${durationSeconds % 60}s` : `${durationSeconds}s`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={handleBackdropClick}
    >
      <div className="bg-background border border-border rounded-lg max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-background border-b border-border p-6 flex items-start justify-between">
          <div className="flex-1">
            <h2 className="text-xl font-bold text-foreground">{data.title || 'Untitled Session'}</h2>
            <p className="text-sm text-muted-foreground mt-1">
              {data.action_mode} • {data.created_at ? new Date(data.created_at).toLocaleString() : 'N/A'}
            </p>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 p-2 hover:bg-muted rounded-full transition-colors"
            aria-label="Close"
          >
            <IconX className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-6">
          {/* Stat Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              icon={IconClock}
              label={t('duration')}
              value={durationText}
              colorClass="bg-blue-500/10 text-blue-500"
            />
            <StatCard
              icon={IconChat}
              label={t('messages')}
              value={data.message_count.toString()}
              subValue={`${data.user_messages}/${data.assistant_messages}`}
              colorClass="bg-green-500/10 text-green-500"
            />
            <StatCard
              icon={IconChart}
              label={t('tokens')}
              value={formatTokenCount(data.totalTokens)}
              subValue={`${(data.cacheHitRate * 100).toFixed(1)}% cached`}
              colorClass="bg-purple-500/10 text-purple-500"
            />
            <StatCard
              icon={IconZap}
              label={t('cost')}
              value={formatCost(data.costUsd)}
              colorClass="bg-orange-500/10 text-orange-500"
            />
          </div>

          <SessionContextHealthPanel health={data.context_health} sessionId={sessionId} />

          {/* Token Economics */}
          {data.token_economics && (
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-foreground">{t('performance')}</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="flex flex-col gap-2 p-4 rounded-xl bg-background/60 border border-border/40">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground font-medium">TTFT Avg</span>
                  </div>
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-xl font-bold tabular-nums text-foreground">
                      {Math.round(data.token_economics.latency.avg_ttft_ms)}
                    </span>
                    <span className="text-xs text-muted-foreground">ms</span>
                  </div>
                </div>
                <div className="flex flex-col gap-2 p-4 rounded-xl bg-background/60 border border-border/40">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground font-medium">P95</span>
                  </div>
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-xl font-bold tabular-nums text-foreground">
                      {Math.round(data.token_economics.latency.p95_ms)}
                    </span>
                    <span className="text-xs text-muted-foreground">ms</span>
                  </div>
                </div>
                <div className="flex flex-col gap-2 p-4 rounded-xl bg-background/60 border border-border/40">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground font-medium">TPS</span>
                  </div>
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-xl font-bold tabular-nums text-foreground">
                      {Math.round(data.token_economics.latency.avg_tokens_per_second)}
                    </span>
                    <span className="text-xs text-muted-foreground">/s</span>
                  </div>
                </div>
                <div className="flex flex-col gap-2 p-4 rounded-xl bg-background/60 border border-border/40">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground font-medium">Avg Latency</span>
                  </div>
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-xl font-bold tabular-nums text-foreground">
                      {Math.round(data.token_economics.latency.avg_ms)}
                    </span>
                    <span className="text-xs text-muted-foreground">ms</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          <ExecutionTraceTimeline sessionId={sessionId} />

          {/* Tool Breakdown */}
          {data.tool_breakdown && data.tool_breakdown.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-foreground">{t('toolBreakdown')}</h3>
              <div className="space-y-2">
                {data.tool_breakdown.map((tool, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-3 bg-background/60 border border-border/40 rounded-lg"
                  >
                    <span className="text-sm font-medium text-foreground">{tool.tool_name}</span>
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span>{tool.call_count} calls</span>
                      <span>{Math.round(tool.total_duration_ms)}ms total</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Events Timeline */}
          {data.events_timeline && data.events_timeline.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-foreground">{t('eventsTimeline')}</h3>
              <div className="space-y-1 max-h-60 overflow-y-auto">
                {data.events_timeline.slice(0, 50).map((event, idx) => (
                  <div
                    key={idx}
                    className="flex items-start gap-3 p-2 text-xs hover:bg-muted/50 rounded transition-colors"
                  >
                    <span className="text-muted-foreground font-mono shrink-0">
                      {new Date(event.timestamp * 1000).toLocaleTimeString()}
                    </span>
                    <span className="font-medium text-foreground">{event.type}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
});
SessionAnalyticsDialog.displayName = 'SessionAnalyticsDialog';

interface StatCardProps {
  icon: React.ElementType;
  label: string;
  value: string;
  subValue?: string;
  colorClass: string;
}

const StatCard = memo<StatCardProps>(({ icon: Icon, label, value, subValue, colorClass }) => (
  <div className="flex flex-col gap-2 p-4 rounded-xl bg-background/60 border border-border/40">
    <div className="flex items-center gap-2">
      <div className={cn('w-8 h-8 rounded-lg flex items-center justify-center', colorClass)}>
        <Icon className="w-4 h-4 text-inherit" />
      </div>
      <span className="text-xs text-muted-foreground font-medium">{label}</span>
    </div>
    <div className="flex items-baseline gap-1.5">
      <span className="text-xl font-bold tabular-nums text-foreground">{value}</span>
      {subValue && <span className="text-xs text-muted-foreground">{subValue}</span>}
    </div>
  </div>
));
StatCard.displayName = 'StatCard';

export default SessionAnalyticsDialog;
