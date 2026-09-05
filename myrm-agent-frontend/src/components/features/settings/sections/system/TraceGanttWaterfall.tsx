'use client';

import { memo, useMemo, useState } from 'react';
import {
  IconBrain,
  IconCheckCircle,
  IconClock,
  IconShield,
  IconWrench,
  IconXCircle,
} from '@/components/features/icons/PremiumIcons';
import type { TracePerformanceSummary, GanttSpan } from '@/services/statistics';
import { cn } from '@/lib/utils/classnameUtils';

interface TraceGanttWaterfallProps {
  performance?: TracePerformanceSummary;
  totalDurationMs: number;
}

const DEFAULT_VISIBLE_SPANS = 6;

const TraceGanttWaterfall = memo<TraceGanttWaterfallProps>(({ performance, totalDurationMs }) => {
  const [privacyMode, setPrivacyMode] = useState(false);
  const [selectedSpan, setSelectedSpan] = useState<GanttSpan | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);

  const spans = performance?.gantt_spans || [];

  const { minStart, timeRange } = useMemo(() => {
    if (spans.length === 0) {
      return { minStart: 0, timeRange: Math.max(totalDurationMs, 1) };
    }
    const starts = spans.map((s) => s.start_time);
    const ends = spans.map((s) => s.end_time);
    const minS = Math.min(...starts);
    const maxE = Math.max(...ends);
    const range = Math.max(maxE - minS, 0.001);
    return { minStart: minS, timeRange: range };
  }, [spans, totalDurationMs]);

  const llmDuration = performance?.llm_duration_ms || 0;
  const toolDuration = performance?.tool_duration_ms || 0;
  const totalCombined = Math.max(llmDuration + toolDuration, 1);
  const llmRatio = Math.round((llmDuration / totalCombined) * 100);
  const toolRatio = 100 - llmRatio;

  const totalPrompt = performance?.total_prompt_tokens || 0;
  const totalCacheRead = performance?.total_cache_read_tokens || 0;
  const hitRatioPercent = Math.round((performance?.prompt_cache_hit_ratio || 0) * 100);

  const visibleSpans = isExpanded ? spans : spans.slice(0, DEFAULT_VISIBLE_SPANS);

  return (
    <div
      data-testid="trace-gantt-waterfall"
      className="rounded-xl border border-border/50 bg-background/50 p-4 space-y-4 backdrop-blur-sm"
    >
      {/* Header with Title and Privacy Toggle */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/30 pb-3">
        <div className="flex items-center gap-2">
          <IconClock className="h-4 w-4 text-primary" />
          <h4 className="text-sm font-semibold text-foreground tracking-tight">
            Execution Waterfall ({spans.length} spans)
          </h4>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setPrivacyMode((v) => !v)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors border',
              privacyMode
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400'
                : 'bg-muted/60 border-border/40 text-muted-foreground hover:text-foreground',
            )}
          >
            <IconShield className="h-3.5 w-3.5" />
            <span>Privacy Mode</span>
          </button>
        </div>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Timing Breakdown */}
        <div className="rounded-lg border border-border/40 bg-muted/20 p-3 space-y-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span className="flex items-center gap-1 font-medium">
              <span className="h-2 w-2 rounded-full bg-violet-500" />
              LLM {llmRatio}%
            </span>
            <span className="flex items-center gap-1 font-medium">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              Tool {toolRatio}%
            </span>
          </div>
          <div className="h-2 w-full rounded-full bg-muted overflow-hidden flex">
            <div
              className="h-full bg-linear-to-r from-violet-600 to-indigo-500 transition-all duration-300"
              style={{ width: `${llmRatio}%` }}
            />
            <div
              className="h-full bg-linear-to-r from-emerald-500 to-teal-400 transition-all duration-300"
              style={{ width: `${toolRatio}%` }}
            />
          </div>
          <div className="flex justify-between text-[11px] text-muted-foreground font-mono">
            <span>{Math.round(llmDuration)} ms</span>
            <span>{Math.round(toolDuration)} ms</span>
          </div>
        </div>

        {/* Prompt Cache Badge (Rendered only when prompt tokens exist) */}
        {totalPrompt > 0 && (
          <div
            data-testid="prompt-cache-badge"
            className="rounded-lg border border-border/40 bg-muted/20 p-3 flex items-center justify-between"
          >
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground font-medium">Prompt Cache: {hitRatioPercent}%</div>
              <div className="flex items-baseline gap-1.5 text-xs text-muted-foreground font-mono">
                <span>
                  ({totalCacheRead.toLocaleString()} / {totalPrompt.toLocaleString()})
                </span>
              </div>
            </div>
            <div
              className={cn(
                'h-10 w-10 rounded-full flex items-center justify-center border font-mono text-xs font-semibold',
                hitRatioPercent > 60
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400'
                  : hitRatioPercent > 20
                    ? 'bg-blue-500/10 border-blue-500/30 text-blue-600 dark:text-blue-400'
                    : 'bg-muted border-border/60 text-muted-foreground',
              )}
            >
              {hitRatioPercent > 0 ? `+${hitRatioPercent}%` : '0%'}
            </div>
          </div>
        )}
      </div>

      {/* Waterfall Spans */}
      {spans.length > 0 && (
        <div className="space-y-2 pt-1">
          <div className="flex justify-between text-[10px] text-muted-foreground/70 font-mono px-1">
            <span>0ms</span>
            <span>{Math.round(timeRange * 1000)}ms</span>
          </div>

          <div className="space-y-1.5">
            {visibleSpans.map((span, idx) => {
              const leftPercent = Math.max(0, Math.min(100, ((span.start_time - minStart) / timeRange) * 100));
              const rawWidthPercent = ((span.end_time - span.start_time) / timeRange) * 100;
              const widthPercent = Math.max(2, Math.min(100 - leftPercent, rawWidthPercent));

              const isLLM = span.type === 'llm';
              const isError = span.status === 'error';

              return (
                <div
                  key={idx}
                  onClick={() => setSelectedSpan(span)}
                  className="group relative h-7 w-full rounded bg-muted/30 hover:bg-muted/60 transition-colors cursor-pointer flex items-center px-2"
                >
                  <div
                    className={cn(
                      'absolute h-4.5 rounded transition-all shadow-xs flex items-center px-1.5 overflow-hidden',
                      isLLM
                        ? 'bg-indigo-500/80 dark:bg-indigo-600/80 text-white'
                        : isError
                          ? 'bg-rose-500/80 dark:bg-rose-600/80 text-white'
                          : 'bg-emerald-500/80 dark:bg-emerald-600/80 text-white',
                    )}
                    style={{ left: `${leftPercent}%`, width: `${widthPercent}%` }}
                  >
                    <span className="text-[10px] font-medium truncate font-mono">
                      {Math.round(span.duration_ms)}ms
                    </span>
                  </div>

                  <div className="relative z-10 flex items-center gap-1.5 text-xs text-foreground/80 pointer-events-none">
                    {isLLM ? (
                      <IconBrain className="h-3 w-3 text-indigo-400" />
                    ) : (
                      <IconWrench className="h-3 w-3 text-emerald-400" />
                    )}
                    <span className="font-medium truncate max-w-[140px] text-[11px]">
                      {privacyMode ? (isLLM ? 'LLM' : 'Tool') : span.label}
                    </span>
                  </div>

                  <div className="ml-auto relative z-10 flex items-center gap-1 text-[11px] text-muted-foreground font-mono">
                    {isError ? (
                      <IconXCircle className="h-3 w-3 text-rose-500" />
                    ) : (
                      <IconCheckCircle className="h-3 w-3 text-emerald-500" />
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Expand / Collapse Button */}
          {spans.length > DEFAULT_VISIBLE_SPANS && (
            <div className="pt-2 text-center">
              <button
                type="button"
                onClick={() => setIsExpanded((prev) => !prev)}
                className="text-xs text-primary hover:text-primary/80 font-medium px-3 py-1 rounded-md bg-muted/40 hover:bg-muted/80 transition-colors"
              >
                {isExpanded ? 'Collapse' : `Show all ${spans.length}`}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Selected Span Detail Popover */}
      {selectedSpan && (
        <div className="rounded-lg border border-border/50 bg-background/80 p-2.5 text-xs space-y-1">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-foreground flex items-center gap-1">
              <IconClock className="h-3.5 w-3.5 text-primary" />
              {privacyMode ? 'Protected Span' : selectedSpan.label}
            </span>
            <span className="font-mono text-muted-foreground">{Math.round(selectedSpan.duration_ms)} ms</span>
          </div>
          {selectedSpan.ttft_ms && selectedSpan.ttft_ms > 0 && (
            <div className="text-muted-foreground font-mono text-[11px]">
              TTFT: {Math.round(selectedSpan.ttft_ms)} ms
            </div>
          )}
          {selectedSpan.error && (
            <div className="text-rose-500 text-[11px] break-words">{selectedSpan.error}</div>
          )}
        </div>
      )}
    </div>
  );
});

TraceGanttWaterfall.displayName = 'TraceGanttWaterfall';

export default TraceGanttWaterfall;
