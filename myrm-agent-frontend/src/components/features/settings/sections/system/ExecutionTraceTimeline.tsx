'use client';

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconBrain,
  IconCheckCircle,
  IconChevronDown,
  IconChevronRight,
  IconClock,
  IconLoader,
  IconMessageSquare,
  IconPlay,
  IconShieldAlert,
  IconSquare,
  IconWrench,
  IconXCircle,
} from '@/components/features/icons/PremiumIcons';
import {
  getSessionExecutionTrace,
  type ExecutionTrace,
  type TraceToolCall,
  type TraceOutcome,
} from '@/services/statistics';
import { cn } from '@/lib/utils/classnameUtils';

import SaveEvalCase from '@/components/features/message-actions/SaveEvalCase';
import useChatStore from '@/store/useChatStore';
import SessionReplayPlayer from '@/components/features/memory/replay/SessionReplayPlayer';
import TraceErrorItem from './TraceErrorItem';
import TraceLLMCallItem from './TraceLLMCallItem';
import TraceGanttWaterfall from './TraceGanttWaterfall';

interface ExecutionTraceTimelineProps {
  sessionId: string;
  /**
   * Kanban task runs have no Chat record, so the "save as eval case" action
   * (which replays chat messages) would always fail; callers may hide it.
   */
  showEvalCase?: boolean;
  /**
   * Optional live-refresh interval (ms) for in-progress runs. While the run is
   * running the trace grows incrementally; callers pass a value here and drop it
   * once the run reaches a terminal state.
   */
  pollMs?: number;
}

const OUTCOME_CONFIG: Record<TraceOutcome, { icon: React.ElementType; label: string; className: string }> = {
  success: {
    icon: IconCheckCircle,
    label: 'success',
    className: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  },
  failure: {
    icon: IconXCircle,
    label: 'failure',
    className: 'bg-rose-500/15 text-rose-600 dark:text-rose-400',
  },
  cancelled: {
    icon: IconSquare,
    label: 'cancelled',
    className: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  },
  unknown: {
    icon: IconClock,
    label: 'unknown',
    className: 'bg-muted text-muted-foreground',
  },
};

function isDenyDecision(decision: string): boolean {
  return /DENY|BLOCK|BREAK|STOP|REJECT/i.test(decision);
}

const ExecutionTraceTimeline = memo<ExecutionTraceTimelineProps>(({ sessionId, showEvalCase = true, pollMs }) => {
  const t = useTranslations('settings.sessionAnalytics.trace');
  const [trace, setTrace] = useState<ExecutionTrace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [replayMode, setReplayMode] = useState(false);
  const [viewMode, setViewMode] = useState<'gantt' | 'list'>('gantt');

  const activeSessionAnalyticsMessageId = useChatStore((state) => state.activeSessionAnalyticsMessageId);
  const messages = useChatStore((state) => state.messages);
  const activeMessage = messages.find((m) => m.messageId === activeSessionAnalyticsMessageId && m.role === 'assistant');

  const highlightedTools = activeMessage?.tokenEconomics?.tool_breakdown
    ? Object.keys(activeMessage.tokenEconomics.tool_breakdown)
    : [];

  const highlightedModels = activeMessage?.tokenEconomics?.model_breakdown
    ? Object.keys(activeMessage.tokenEconomics.model_breakdown)
    : [];

  const { totalPrompt, totalCacheRead, cacheHitRatio } = useMemo(() => {
    let prompt = trace?.prompt_tokens ?? 0;
    let cache = trace?.cache_read_tokens ?? 0;
    if (!prompt && trace?.llm_calls) {
      prompt = trace.llm_calls.reduce((s, c) => s + (c.prompt_tokens || 0), 0);
      cache = trace.llm_calls.reduce((s, c) => s + (c.cache_read_tokens || 0), 0);
    }
    const ratio = prompt > 0 ? Math.round((cache / prompt) * 1000) / 10 : 0;
    return { totalPrompt: prompt, totalCacheRead: cache, cacheHitRatio: ratio };
  }, [trace]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | undefined;
    const load = async (initial: boolean) => {
      try {
        if (initial) {
          setLoading(true);
          setError(null);
        }
        const data = await getSessionExecutionTrace(sessionId);
        if (!cancelled) {
          setTrace(data);
        }
      } catch (err) {
        if (!cancelled && initial) {
          setError(err instanceof Error ? err.message : 'Failed to load trace');
        }
      } finally {
        if (!cancelled && initial) {
          setLoading(false);
        }
      }
    };
    void load(true);
    if (pollMs && pollMs > 0) {
      timer = setInterval(() => void load(false), pollMs);
    }
    return () => {
      cancelled = true;
      if (timer) {
        clearInterval(timer);
      }
    };
  }, [sessionId, pollMs]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
        <IconLoader className="h-4 w-4 animate-spin" />
        {t('loading')}
      </div>
    );
  }

  if (error || !trace) {
    return null;
  }

  if (replayMode) {
    return (
      <div className="space-y-3">
        <div className="flex justify-end">
          <button
            onClick={() => setReplayMode(false)}
            className="text-xs bg-muted hover:bg-muted/80 text-foreground px-3 py-1.5 rounded-full transition-colors"
          >
            {t('exitReplay', { defaultMessage: 'Exit Replay Mode' })}
          </button>
        </div>
        <SessionReplayPlayer sessionId={sessionId} trace={trace} />
      </div>
    );
  }

  const outcomeConfig = OUTCOME_CONFIG[trace.outcome];
  const OutcomeIcon = outcomeConfig.icon;

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-foreground">{t('title')}</h3>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setReplayMode(true)}
            className="text-xs bg-blue-500/10 hover:bg-blue-500/20 text-blue-600 dark:text-blue-400 px-3 py-1 rounded-full font-medium transition-colors flex items-center gap-1 border border-blue-500/20"
          >
            <IconPlay className="w-3 h-3" />
            {t('enterReplay', { defaultMessage: 'Enter Replay' })}
          </button>
          {trace.outcome === 'failure' && showEvalCase && (
            <div className="mr-2" title={t('saveAsEval', { defaultMessage: 'Save as Eval Case' })}>
              <SaveEvalCase chatId={sessionId} />
            </div>
          )}
          <span
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium',
              outcomeConfig.className,
            )}
          >
            <OutcomeIcon className="h-3.5 w-3.5" />
            {t(`outcome.${outcomeConfig.label}`)}
          </span>
        </div>
      </div>

      {trace.task_input && (
        <div className="rounded-lg border border-border/40 bg-background/60 p-3">
          <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1.5">
            <IconPlay className="h-3 w-3" />
            {t('input')}
          </div>
          <p className="text-sm text-foreground line-clamp-3">{trace.task_input}</p>
        </div>
      )}

      {trace.performance_summary && (
        <TraceGanttWaterfall performance={trace.performance_summary} totalDurationMs={trace.duration_ms} />
      )}

      {trace.tool_calls && trace.tool_calls.length > 0 && (
        <div className="space-y-1">
          {trace.tool_calls.map((tc, idx) => (
            <ToolCallItem
              key={`tc-${tc.sequence}-${idx}`}
              toolCall={tc}
              traceStartTime={trace.start_time}
              isHighlighted={highlightedTools.some((ht) => {
                const normHt = ht.toLowerCase().replace(/[^a-z0-9]/g, '');
                const normTc = tc.tool_name.toLowerCase().replace(/[^a-z0-9]/g, '');
                return (
                  normHt === normTc ||
                  ht.toLowerCase().includes(tc.tool_name.toLowerCase()) ||
                  tc.tool_name.toLowerCase().includes(ht.toLowerCase())
                );
              })}
            />
          ))}
        </div>
      )}

      {trace.llm_calls && trace.llm_calls.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-semibold text-muted-foreground mb-2 mt-4 px-1">
            {t('llmCalls', { defaultMessage: 'LLM Invocations' })}
          </div>
          {trace.llm_calls.map((lc, idx) => (
            <TraceLLMCallItem
              key={`lc-${lc.sequence}-${idx}`}
              llmCall={lc}
              isHighlighted={highlightedModels.some((hm) => {
                const normHm = hm.toLowerCase().split('/').pop();
                const normLc = (lc.model_name || '').toLowerCase().split('/').pop();
                return (
                  normHm === normLc ||
                  hm.toLowerCase().includes((lc.model_name || '').toLowerCase()) ||
                  (lc.model_name || '').toLowerCase().includes(hm.toLowerCase())
                );
              })}
            />
          ))}
        </div>
      )}

      {trace.errors && trace.errors.length > 0 && (
        <div className="space-y-1">
          {trace.errors.map((err, idx) => (
            <TraceErrorItem
              key={`err-${idx}-${err.timestamp}`}
              error={err}
              isFirstIrrecoverable={trace.first_irrecoverable_index === idx}
            />
          ))}
        </div>
      )}

      {trace.human_feedback.length > 0 && (
        <div className="space-y-1">
          {trace.human_feedback.map((fb, idx) => (
            <div key={idx} className="flex items-center gap-3 p-2.5 rounded-lg bg-blue-500/5 border border-blue-500/20">
              <IconMessageSquare className="h-3.5 w-3.5 shrink-0 text-blue-500" />
              <span className="text-xs text-foreground">
                {fb.tool_name && <span className="font-medium">{fb.tool_name}</span>}
                {fb.approved !== null && (
                  <span className={cn('ml-2', fb.approved ? 'text-emerald-600' : 'text-rose-600')}>
                    {fb.approved ? t('approved') : t('rejected')}
                  </span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}

      {trace.memory_events && trace.memory_events.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-semibold text-muted-foreground mb-2 mt-4 px-1 flex items-center gap-1.5">
            <IconBrain className="w-3.5 h-3.5 text-purple-500" />
            <span>{t('memoryEvents', { defaultMessage: 'Context Injections & Memory' })}</span>
          </div>
          {trace.memory_events.map((me, idx) => (
            <div
              key={`me-${me.id || idx}`}
              className="rounded-lg border border-purple-500/20 bg-purple-500/5 p-2.5 transition-all text-xs"
            >
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="font-medium text-foreground">{me.title || me.phase}</span>
                {me.influence_count > 0 && (
                  <span className="text-[10px] bg-purple-500/10 text-purple-600 dark:text-purple-400 px-2 py-0.5 rounded-full font-medium">
                    {t('influenceCount', {
                      count: me.influence_count,
                      defaultMessage: `Influenced turns: ${me.influence_count}`,
                    })}
                  </span>
                )}
              </div>
              {me.summary && (
                <p className="text-muted-foreground text-[11px] leading-relaxed line-clamp-2">{me.summary}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {trace.output && (
        <div className="rounded-lg border border-border/40 bg-background/60 p-3">
          <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1.5">
            <IconSquare className="h-3 w-3" />
            {t('output')}
          </div>
          <p className="text-sm text-foreground line-clamp-3">{trace.output}</p>
        </div>
      )}

      <div className="flex items-center gap-4 text-xs text-muted-foreground pt-1">
        <span>
          {trace.total_events} {t('events')}
        </span>
        {trace.total_tokens > 0 && <span>{trace.total_tokens.toLocaleString()} tokens</span>}
        {trace.duration_ms > 0 && (
          <span>
            {trace.duration_ms >= 60000
              ? `${Math.floor(trace.duration_ms / 60000)}m ${Math.round((trace.duration_ms % 60000) / 1000)}s`
              : `${(trace.duration_ms / 1000).toFixed(1)}s`}
          </span>
        )}
      </div>
    </section>
  );
});
ExecutionTraceTimeline.displayName = 'ExecutionTraceTimeline';

interface ToolCallItemProps {
  toolCall: TraceToolCall;
  traceStartTime: number;
  isHighlighted?: boolean;
}

const ToolCallItem = memo<ToolCallItemProps>(({ toolCall, traceStartTime, isHighlighted }) => {
  const [expanded, setExpanded] = useState(false);
  const toggle = useCallback(() => setExpanded((prev) => !prev), []);
  const tFault = useTranslations('progressSteps');
  const tSecurity = useTranslations('settings.sessionAnalytics.trace');
  const faultSide = toolCall.fault_side && toolCall.fault_side !== 'unknown' ? toolCall.fault_side : null;

  const securityLabels = toolCall.security_labels ?? [];
  const hasSecurity = securityLabels.length > 0;
  const critical = hasSecurity && securityLabels.some((s) => s.tainted || isDenyDecision(s.decision));

  const offsetMs = Math.max(0, Math.round((toolCall.start_time - traceStartTime) * 1000));
  const offsetText = offsetMs >= 1000 ? `+${(offsetMs / 1000).toFixed(1)}s` : `+${offsetMs}ms`;

  const durationText = toolCall.duration_ms
    ? toolCall.duration_ms >= 1000
      ? `${(toolCall.duration_ms / 1000).toFixed(1)}s`
      : `${Math.round(toolCall.duration_ms)}ms`
    : null;

  const Chevron = expanded ? IconChevronDown : IconChevronRight;

  return (
    <div
      className={cn(
        'rounded-lg border transition-all duration-300 relative overflow-hidden',
        isHighlighted
          ? 'border-amber-500/60 dark:border-amber-500/40 bg-amber-50/10 dark:bg-amber-500/5 shadow-[0_0_12px_rgba(245,158,11,0.15)] ring-1 ring-amber-500/20'
          : toolCall.success
            ? 'border-border/40 bg-background/60 hover:bg-muted/30'
            : 'border-rose-500/30 bg-rose-500/5',
      )}
    >
      {isHighlighted && (
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-amber-400 via-amber-500 to-amber-600" />
      )}
      <button onClick={toggle} className="w-full flex items-center gap-3 p-2.5 text-left">
        <Chevron className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <IconWrench className={cn('h-3.5 w-3.5 shrink-0', toolCall.success ? 'text-emerald-500' : 'text-rose-500')} />
        <span className="text-sm font-medium text-foreground truncate flex-1">{toolCall.tool_name}</span>
        <div className="flex items-center gap-3 text-xs text-muted-foreground shrink-0">
          <span className="font-mono">{offsetText}</span>
          {durationText && <span className="font-mono">{durationText}</span>}
          {hasSecurity && (
            <span
              className={cn(
                'inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full border font-medium',
                critical
                  ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30'
                  : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30',
              )}
              title={securityLabels.map((s) => `${s.decision}: ${s.reason ?? ''}`).join('\n')}
            >
              <IconShieldAlert className="h-3 w-3" />
              {tSecurity('securityFlag')}
            </span>
          )}
          {toolCall.success ? (
            <IconCheckCircle className="h-3.5 w-3.5 text-emerald-500" />
          ) : (
            <IconXCircle className="h-3.5 w-3.5 text-rose-500" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="space-y-2 pb-2.5">
          {hasSecurity && (
            <div className="px-10">
              <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                {tSecurity('securityLabels')}
              </p>
              <div className="space-y-1">
                {securityLabels.map((label, idx) => (
                  <div
                    key={idx}
                    className={cn(
                      'flex items-start gap-2 rounded-md border px-2 py-1.5 text-xs',
                      label.tainted || isDenyDecision(label.decision)
                        ? 'border-rose-500/25 bg-rose-500/5'
                        : 'border-amber-500/25 bg-amber-500/5',
                    )}
                  >
                    <IconShieldAlert
                      className={cn(
                        'h-3.5 w-3.5 shrink-0 mt-0.5',
                        label.tainted || isDenyDecision(label.decision) ? 'text-rose-500' : 'text-amber-500',
                      )}
                    />
                    <div className="min-w-0">
                      <span className="font-medium text-foreground">{label.decision}</span>
                      {label.reason && <span className="ml-2 text-muted-foreground break-words">{label.reason}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {toolCall.error && (
            <div className="px-10">
              {faultSide && (
                <span className="mb-1.5 inline-flex items-center rounded-full bg-rose-500/10 border border-rose-500/25 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-rose-600 dark:text-rose-400">
                  {tFault(`faultSides.${faultSide}`)}
                </span>
              )}
              <p className="text-xs text-rose-600 dark:text-rose-400 break-words">{toolCall.error}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
});
ToolCallItem.displayName = 'ToolCallItem';

export default ExecutionTraceTimeline;
