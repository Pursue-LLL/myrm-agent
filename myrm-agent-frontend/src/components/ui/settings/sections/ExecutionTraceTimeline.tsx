'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconAlertTriangle,
  IconCheckCircle,
  IconChevronDown,
  IconChevronRight,
  IconClock,
  IconLoader,
  IconMessageSquare,
  IconPlay,
  IconSquare,
  IconWrench,
  IconXCircle,
} from '@/components/ui/icons/PremiumIcons';
import {
  getSessionExecutionTrace,
  type ExecutionTrace,
  type TraceToolCall,
  type TraceLLMCall,
  type TraceOutcome,
} from '@/services/statistics';
import { cn } from '@/lib/utils/classnameUtils';

import SaveEvalCase from '@/components/ui/message-actions/SaveEvalCase';
import useChatStore from '@/store/useChatStore';
import SessionReplayPlayer from '@/components/ui/memory/SessionReplayPlayer';

interface ExecutionTraceTimelineProps {
  sessionId: string;
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

const ExecutionTraceTimeline = memo<ExecutionTraceTimelineProps>(({ sessionId }) => {
  const t = useTranslations('settings.sessionAnalytics.trace');
  const [trace, setTrace] = useState<ExecutionTrace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [replayMode, setReplayMode] = useState(false);

  const activeSessionAnalyticsMessageId = useChatStore((state) => state.activeSessionAnalyticsMessageId);
  const messages = useChatStore((state) => state.messages);
  const activeMessage = messages.find((m) => m.messageId === activeSessionAnalyticsMessageId);

  const highlightedTools = activeMessage?.tokenEconomics?.tool_breakdown
    ? Object.keys(activeMessage.tokenEconomics.tool_breakdown)
    : [];

  const highlightedModels = activeMessage?.tokenEconomics?.model_breakdown
    ? Object.keys(activeMessage.tokenEconomics.model_breakdown)
    : [];

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await getSessionExecutionTrace(sessionId);
        if (!cancelled) setTrace(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load trace');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

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
          {trace.outcome === 'failure' && (
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
            <LLMCallItem
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
            <div key={idx} className="flex items-start gap-3 p-2.5 rounded-lg bg-rose-500/5 border border-rose-500/20">
              <IconAlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-rose-500" />
              <div className="min-w-0">
                <span className="text-xs font-medium text-rose-600 dark:text-rose-400">{String(err.error_type)}</span>
                <p className="text-xs text-muted-foreground mt-0.5 break-words">{String(err.error)}</p>
              </div>
            </div>
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
          {toolCall.success ? (
            <IconCheckCircle className="h-3.5 w-3.5 text-emerald-500" />
          ) : (
            <IconXCircle className="h-3.5 w-3.5 text-rose-500" />
          )}
        </div>
      </button>

      {expanded && toolCall.error && (
        <div className="px-10 pb-2.5">
          <p className="text-xs text-rose-600 dark:text-rose-400 break-words">{toolCall.error}</p>
        </div>
      )}
    </div>
  );
});
ToolCallItem.displayName = 'ToolCallItem';

export default ExecutionTraceTimeline;

interface LLMCallItemProps {
  llmCall: TraceLLMCall;
  isHighlighted?: boolean;
}

const LLMCallItem = memo<LLMCallItemProps>(({ llmCall, isHighlighted }) => {
  const { duration_ms, ttft_ms, model_name, prompt_tokens, completion_tokens, total_tokens } = llmCall;

  const hasLatencyData = duration_ms !== null && ttft_ms !== null && duration_ms > 0;
  let ttftRatio = 0;
  let genRatio = 0;
  let tps = 0;

  if (hasLatencyData) {
    const validTtft = Math.min(ttft_ms!, duration_ms!);
    const genMs = Math.max(0, duration_ms! - validTtft);
    ttftRatio = (validTtft / duration_ms!) * 100;
    genRatio = (genMs / duration_ms!) * 100;
    if (genMs > 0 && completion_tokens > 0) {
      tps = completion_tokens / (genMs / 1000);
    }
  }

  const durationText = duration_ms
    ? duration_ms >= 1000
      ? `${(duration_ms / 1000).toFixed(1)}s`
      : `${Math.round(duration_ms)}ms`
    : '-';

  return (
    <div
      className={cn(
        'rounded-lg border p-2.5 transition-all duration-300 relative overflow-hidden',
        isHighlighted
          ? 'border-amber-500/60 dark:border-amber-500/40 bg-amber-50/10 dark:bg-amber-500/5 shadow-[0_0_12px_rgba(245,158,11,0.15)] ring-1 ring-amber-500/20'
          : 'border-border/40 bg-background/60',
      )}
    >
      {isHighlighted && (
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-amber-400 via-amber-500 to-amber-600" />
      )}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <IconClock className="w-3.5 h-3.5 text-blue-500" />
          <span className="text-sm font-medium text-foreground">{model_name || 'Unknown Model'}</span>
        </div>
        <div className="text-xs text-muted-foreground flex gap-3">
          <span>{total_tokens.toLocaleString()} tokens</span>
          <span className="font-mono">{durationText}</span>
        </div>
      </div>

      {hasLatencyData && (
        <div className="space-y-1.5 mt-2">
          <div className="flex w-full h-1.5 rounded-full overflow-hidden bg-muted">
            <div
              className="h-full bg-amber-400 dark:bg-amber-500/80 transition-all"
              style={{ width: `${ttftRatio}%` }}
              title={`Network Wait (TTFT): ${Math.round(ttft_ms!)}ms`}
            />
            <div
              className="h-full bg-emerald-400 dark:bg-emerald-500/80 transition-all"
              style={{ width: `${genRatio}%` }}
              title={`Token Generation: ${Math.round(duration_ms! - ttft_ms!)}ms`}
            />
          </div>
          <div className="flex justify-between text-[10px] text-muted-foreground px-0.5">
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 dark:bg-amber-500/80" />
              TTFT: {Math.round(ttft_ms!)}ms
            </span>
            <span className="flex items-center gap-3">
              <span className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 dark:bg-emerald-500/80" />
                Gen: {Math.round(duration_ms! - ttft_ms!)}ms
              </span>
              {tps > 0 && (
                <span className="font-mono text-emerald-600 dark:text-emerald-400">{tps.toFixed(1)} tps</span>
              )}
            </span>
          </div>
        </div>
      )}

      <div className="flex gap-4 mt-2 text-[10px] text-muted-foreground/70">
        <span>Prompt: {prompt_tokens}</span>
        <span>Completion: {completion_tokens}</span>
        {llmCall.message_count != null && <span>Messages: {llmCall.message_count}</span>}
      </div>

      {llmCall.prompt_preview && (
        <p className="mt-1.5 text-[10px] text-muted-foreground/60 line-clamp-2 italic">{llmCall.prompt_preview}</p>
      )}
    </div>
  );
});
LLMCallItem.displayName = 'LLMCallItem';
