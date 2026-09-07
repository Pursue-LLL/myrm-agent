'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconX,
  IconClock,
  IconChat,
  IconChart,
  IconZap,
  IconAlertCircle,
  IconShieldAlert,
  IconCopy,
  IconCheck,
  IconDownload,
} from '@/components/features/icons/PremiumIcons';
import { getSessionAnalytics, type SessionAnalytics } from '@/services/statistics';
import { formatCost, formatTokenCount } from './RoutingAnalyticsPanel';
import { cn } from '@/lib/utils/classnameUtils';
import SessionContextHealthPanel from './SessionContextHealthPanel';
import ExecutionTraceTimeline from './ExecutionTraceTimeline';
import ContextBreakdownCard from './ContextBreakdownCard';

interface SessionAnalyticsDialogProps {
  sessionId: string;
  onClose: () => void;
}

const SessionAnalyticsDialog = memo<SessionAnalyticsDialogProps>(({ sessionId, onClose }) => {
  const t = useTranslations('settings.sessionAnalytics');
  const tm = useTranslations('mode');
  const [data, setData] = useState<SessionAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleCopyMarkdown = useCallback(async () => {
    if (!data) return;
    const durSec = Math.round(data.duration_ms / 1000);
    const durStr = durSec >= 60 ? `${Math.floor(durSec / 60)}m ${durSec % 60}s` : `${durSec}s`;

    const llmRows =
      data.llm_breakdown && data.llm_breakdown.length > 0
        ? data.llm_breakdown
            .map(
              (item) =>
                `| ${item.model_name} | ${item.call_count} | ${item.total_duration_ms} ms | ${item.call_count > 0 ? Math.round(item.total_duration_ms / item.call_count) : 0} ms |`,
            )
            .join('\n')
        : '| N/A | 0 | 0 ms | 0 ms |';

    const toolRows =
      data.tool_breakdown && data.tool_breakdown.length > 0
        ? data.tool_breakdown
            .map(
              (item) =>
                `| ${item.tool_name} | ${item.call_count} | ${item.total_duration_ms} ms | ${item.call_count > 0 ? Math.round(item.total_duration_ms / item.call_count) : 0} ms |`,
            )
            .join('\n')
        : '| N/A | 0 | 0 ms | 0 ms |';

    const markdown = `# 📋 Myrm Task Audit Ledger

- **Session Title**: ${data.title || 'Untitled Session'}
- **Session ID**: \`${data.session_id}\`
- **Action Mode**: ${data.action_mode}
- **Timestamp**: ${data.created_at ? new Date(data.created_at).toLocaleString() : 'N/A'}
- **Total Duration**: ${durStr}
- **Total Messages**: ${data.message_count} (User: ${data.user_messages}, Assistant: ${data.assistant_messages})
- **Total Tokens**: ${data.total_tokens.toLocaleString()} (Input: ${data.input_tokens.toLocaleString()}, Output: ${data.output_tokens.toLocaleString()}, Cached: ${data.cached_tokens.toLocaleString()})
- **Prompt Cache Hit Ratio**: ${(data.cache_hit_ratio * 100).toFixed(1)}%
- **Estimated Cost**: $${data.cost_usd.toFixed(4)} USD

### 🤖 LLM Breakdown
| Model | Calls | Total Duration | Avg Latency |
| :--- | :--- | :--- | :--- |
${llmRows}

### 🛠️ Tool & Sandbox Breakdown
| Tool Name | Calls | Total Duration | Avg Latency |
| :--- | :--- | :--- | :--- |
${toolRows}
`;

    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
        await navigator.clipboard.writeText(markdown);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
        return;
      }
      throw new Error('Clipboard API unavailable in this context');
    } catch {
      // Insecure context (HTTP LAN) or restricted iframe fallback
      try {
        const textarea = document.createElement('textarea');
        textarea.value = markdown;
        textarea.style.position = 'fixed';
        textarea.style.left = '-9999px';
        textarea.style.top = '-9999px';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        const successful = document.execCommand('copy');
        document.body.removeChild(textarea);
        if (successful) {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        }
      } catch {
        // Silent fallback
      }
    }
  }, [data]);

  const handleDownloadCsv = useCallback(() => {
    if (!data) return;
    const durSec = Math.round(data.duration_ms / 1000);
    const escapeCsv = (val: string | number) => `"${String(val).replace(/"/g, '""')}"`;

    const lines: string[] = [
      '\uFEFFSection,Metric,Value',
      `Session,Title,${escapeCsv(data.title || 'Untitled Session')}`,
      `Session,SessionId,${escapeCsv(data.session_id)}`,
      `Session,Mode,${escapeCsv(data.action_mode)}`,
      `Session,CreatedAt,${escapeCsv(data.created_at || '')}`,
      `Session,DurationSeconds,${durSec}`,
      `Session,TotalMessages,${data.message_count}`,
      `Session,UserMessages,${data.user_messages}`,
      `Session,AssistantMessages,${data.assistant_messages}`,
      `Economics,TotalTokens,${data.total_tokens}`,
      `Economics,InputTokens,${data.input_tokens}`,
      `Economics,OutputTokens,${data.output_tokens}`,
      `Economics,CachedTokens,${data.cached_tokens}`,
      `Economics,CacheHitRatio,${(data.cache_hit_ratio * 100).toFixed(2)}%`,
      `Economics,CostUSD,${data.cost_usd.toFixed(4)}`,
      '',
      'Type,Name,Calls,TotalDurationMs',
    ];

    if (data.llm_breakdown) {
      data.llm_breakdown.forEach((item) => {
        lines.push(`LLM,${escapeCsv(item.model_name)},${item.call_count},${item.total_duration_ms}`);
      });
    }

    if (data.tool_breakdown) {
      data.tool_breakdown.forEach((item) => {
        lines.push(`Tool,${escapeCsv(item.tool_name)},${item.call_count},${item.total_duration_ms}`);
      });
    }

    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `audit-ledger-${data.session_id.slice(0, 8)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [data]);

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
            setError(t('sessionNotFound'));
          } else if (message.includes('access denied') || message.includes('403') || message.includes('forbidden')) {
            setError(t('accessDenied'));
          } else if (message.includes('500') || message.includes('internal')) {
            setError(t('serverError'));
          } else {
            setError(err.message);
          }
        } else {
          setError(t('loadFailed'));
        }
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [sessionId, t]);

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
        role="presentation"
        onClick={handleBackdropClick}
      >
        <div className="bg-background border border-border rounded-lg p-8 max-w-4xl w-full mx-4">
          <div className="flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
        role="presentation"
        onClick={handleBackdropClick}
      >
        <div className="bg-background border border-border rounded-lg p-8 max-w-4xl w-full mx-4">
          <div className="flex items-center gap-2 text-destructive">
            <IconAlertCircle className="w-5 h-5" />
            <span>{error || t('sessionNotFound')}</span>
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
      role="presentation"
      onClick={handleBackdropClick}
    >
      <div className="bg-background border border-border rounded-lg max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-background border-b border-border p-6 flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <h2 className="text-xl font-bold text-foreground truncate">{data.title || t('untitledSession')}</h2>
            <p className="text-sm text-muted-foreground mt-1">
              {tm.has(data.action_mode) ? tm(data.action_mode) : data.action_mode} •{' '}
              {data.created_at ? new Date(data.created_at).toLocaleString() : 'N/A'}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={handleCopyMarkdown}
              className={cn(
                'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all border',
                copied
                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30'
                  : 'bg-muted/60 text-muted-foreground hover:text-foreground hover:bg-muted border-border/60',
              )}
              title={t('copyMarkdownTooltip')}
              aria-label={t('copyMarkdown')}
            >
              {copied ? <IconCheck className="w-3.5 h-3.5 text-emerald-500 shrink-0" /> : <IconCopy className="w-3.5 h-3.5 shrink-0" />}
              <span className="hidden sm:inline">{copied ? t('copied') : t('copyMarkdown')}</span>
            </button>
            <button
              onClick={handleDownloadCsv}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all border bg-muted/60 text-muted-foreground hover:text-foreground hover:bg-muted border-border/60"
              title={t('downloadCsvTooltip')}
              aria-label={t('downloadCsv')}
            >
              <IconDownload className="w-3.5 h-3.5 shrink-0" />
              <span className="hidden sm:inline">{t('downloadCsv')}</span>
            </button>
            <button
              onClick={onClose}
              className="p-1.5 hover:bg-muted rounded-full transition-colors text-muted-foreground hover:text-foreground"
              aria-label={t('close')}
            >
              <IconX className="w-5 h-5" />
            </button>
          </div>
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
              subValue={`${(data.cacheHitRate * 100).toFixed(1)}% ${t('cached')}`}
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
                    <span className="text-xs text-muted-foreground font-medium">{t('tokenTtftAvg')}</span>
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
                    <span className="text-xs text-muted-foreground font-medium">{t('p95')}</span>
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
                    <span className="text-xs text-muted-foreground font-medium">{t('tps')}</span>
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
                    <span className="text-xs text-muted-foreground font-medium">{t('avgLatency')}</span>
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

          {/* Response Speed (per-reply first-token latency) */}
          {data.streamTtft && data.streamTtft.sampleCount > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-foreground">{t('responseSpeed')}</h3>
              <p className="text-xs text-muted-foreground">{t('responseSpeedHint')}</p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="flex flex-col gap-2 p-4 rounded-xl bg-background/60 border border-border/40">
                  <span className="text-xs text-muted-foreground font-medium">{t('ttftAvg')}</span>
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-xl font-bold tabular-nums text-foreground">
                      {Math.round(data.streamTtft.avgMs)}
                    </span>
                    <span className="text-xs text-muted-foreground">ms</span>
                  </div>
                </div>
                <div className="flex flex-col gap-2 p-4 rounded-xl bg-background/60 border border-border/40">
                  <span className="text-xs text-muted-foreground font-medium">{t('ttftP95')}</span>
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-xl font-bold tabular-nums text-foreground">
                      {Math.round(data.streamTtft.p95Ms)}
                    </span>
                    <span className="text-xs text-muted-foreground">ms</span>
                  </div>
                </div>
                <div className="flex flex-col gap-2 p-4 rounded-xl bg-background/60 border border-border/40">
                  <span className="text-xs text-muted-foreground font-medium">{t('samples')}</span>
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-xl font-bold tabular-nums text-foreground">
                      {data.streamTtft.sampleCount}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Context Doctor Breakdown */}
          {data.context_breakdown && (
            <ContextBreakdownCard breakdown={data.context_breakdown} />
          )}

          <ExecutionTraceTimeline sessionId={sessionId} />

          {/* LLM Breakdown */}
          {data.llm_breakdown && data.llm_breakdown.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-foreground">{t('llmBreakdown')}</h3>
              <div className="space-y-2">
                {data.llm_breakdown.map((llm, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-3 bg-background/60 border border-border/40 rounded-lg"
                  >
                    <span className="text-sm font-medium text-foreground">{llm.model_name}</span>
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span>
                        {llm.call_count} {t('calls')}
                      </span>
                      <span>
                        {Math.round(llm.total_duration_ms)}ms {t('total')}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

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
                      <span>
                        {tool.call_count} {t('calls')}
                      </span>
                      <span>
                        {Math.round(tool.total_duration_ms)}ms {t('total')}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Security Audit */}
          {data.security_audit && data.security_audit.total > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                <IconShieldAlert className="h-4 w-4 text-amber-500" />
                {t('securityAudit')}
              </h3>
              <div className="space-y-2">
                {Object.entries(data.security_audit.breakdown as Record<string, number>).map(([kind, count]) => (
                  <div
                    key={kind}
                    className="flex items-center justify-between p-3 bg-background/60 border border-border/40 rounded-lg"
                  >
                    <span
                      className={cn(
                        'text-sm font-medium',
                        kind.includes('BLOCKED') || kind.includes('DENY')
                          ? 'text-destructive'
                          : kind.includes('WARN') || kind.includes('DETECTED')
                            ? 'text-amber-600 dark:text-amber-400'
                            : 'text-foreground',
                      )}
                    >
                      {kind}
                    </span>
                    <span className="text-xs text-muted-foreground tabular-nums">{count}</span>
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
