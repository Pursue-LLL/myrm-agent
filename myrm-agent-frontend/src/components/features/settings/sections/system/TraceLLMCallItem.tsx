'use client';

import { memo } from 'react';
import { IconClock } from '@/components/features/icons/PremiumIcons';
import type { TraceLLMCall } from '@/services/statistics';
import { cn } from '@/lib/utils/classnameUtils';

interface TraceLLMCallItemProps {
  llmCall: TraceLLMCall;
  isHighlighted?: boolean;
}

/**
 * Single LLM invocation card in the execution trace timeline.
 *
 * Shows model, token counts, duration, and a TTFT vs. generation split bar so
 * users can tell "network wait" from "token generation" at a glance.
 */
const TraceLLMCallItem = memo<TraceLLMCallItemProps>(({ llmCall, isHighlighted }) => {
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
TraceLLMCallItem.displayName = 'TraceLLMCallItem';

export default TraceLLMCallItem;
