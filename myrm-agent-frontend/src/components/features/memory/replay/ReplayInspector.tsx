'use client';

/**
 * [INPUT]
 * - memory/replayTimeline::ReplayEvent (POS: Active timeline event for the replay player)
 * - memory/ReplayMessageBubble (POS: Read-only Markdown message rendering)
 *
 * [OUTPUT]
 * - ReplayInspector: detail pane for the active timeline event — errors, tool results, security labels, LLM call stats
 *
 * [POS]
 * Session replay inspector pane. Renders the full payload of the currently active timeline event.
 */

import { useTranslations } from 'next-intl';
import ReplayMessageBubble from '@/components/features/memory/replay/ReplayMessageBubble';
import type { ReplayEvent } from '@/components/features/memory/replay/replayTimeline';

interface ReplayInspectorProps {
  activeEvent: ReplayEvent | null;
}

function ReplayInspector({ activeEvent }: ReplayInspectorProps) {
  const t = useTranslations('settings.sessionAnalytics.replay');

  if (activeEvent?.type === 'error') {
    return (
      <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-full text-xs text-rose-600 dark:text-rose-400 font-mono break-all whitespace-pre-wrap">
        {activeEvent.data.error}
      </div>
    );
  }

  if (activeEvent?.type === 'tool_end' && !activeEvent.data.success) {
    return (
      <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-full text-xs text-rose-600 dark:text-rose-400 font-mono break-all whitespace-pre-wrap">
        {activeEvent.data.error ?? t('toolFailed')}
      </div>
    );
  }

  if (activeEvent?.type === 'human_feedback') {
    const fb = activeEvent.data;
    return (
      <div className="flex flex-col gap-2">
        <div className="text-xs font-medium text-foreground">{t('humanFeedbackTitle')}</div>
        <div className="text-[10px] text-muted-foreground font-mono bg-muted/30 p-2 rounded-full whitespace-pre-wrap break-all">
          {JSON.stringify(fb, null, 2)}
        </div>
      </div>
    );
  }

  if (activeEvent?.type === 'memory') {
    const me = activeEvent.data;
    return (
      <div className="flex flex-col gap-2">
        <div className="text-xs font-medium text-foreground">{t('memoryEventTitle', { phase: me.phase })}</div>
        <div className="text-[10px] text-muted-foreground">
          {me.title === 'pre_compact' ? t('preCompactEventTitle') : me.title}
        </div>
        <div className="text-[10px] text-muted-foreground font-mono bg-muted/30 p-2 rounded-full whitespace-pre-wrap break-all max-h-[200px] overflow-y-auto">
          {me.summary}
        </div>
      </div>
    );
  }

  if (activeEvent?.type === 'llm_call') {
    const lc = activeEvent.data;
    return (
      <div className="flex flex-col gap-2">
        <div className="text-xs font-medium text-foreground">
          {t('llmCallTitle', { model: lc.model_name ?? 'unknown' })}
        </div>
        {lc.prompt_preview && (
          <>
            <div className="text-xs font-medium text-foreground">{t('promptPreview')}</div>
            <div className="text-[10px] text-muted-foreground font-mono bg-muted/30 p-2 rounded-full whitespace-pre-wrap break-all max-h-[160px] overflow-y-auto">
              {lc.prompt_preview}
            </div>
          </>
        )}
        <div className="text-[10px] text-muted-foreground font-mono bg-muted/30 p-2 rounded-full whitespace-pre-wrap break-all">
          {JSON.stringify(
            {
              prompt_tokens: lc.prompt_tokens,
              completion_tokens: lc.completion_tokens,
              total_tokens: lc.total_tokens,
              duration_ms: lc.duration_ms,
              ttft_ms: lc.ttft_ms,
              message_count: lc.message_count,
            },
            null,
            2,
          )}
        </div>
      </div>
    );
  }

  if (activeEvent?.type === 'tool_start' || activeEvent?.type === 'tool_end') {
    const tool = activeEvent.data;
    const securityLabels = tool.security_labels ?? [];
    return (
      <div className="flex flex-col gap-2">
        <div className="text-xs font-medium text-foreground">{t('latestTool', { name: tool.tool_name })}</div>
        {securityLabels.length > 0 && (
          <div className="flex flex-col gap-1">
            <div className="text-xs font-medium text-foreground">{t('securityLabels')}</div>
            {securityLabels.map((label, idx) => (
              <div
                key={`${label.decision}-${idx}`}
                className="flex flex-col gap-0.5 text-[10px] bg-rose-500/10 border border-rose-500/30 rounded-xl px-2 py-1.5"
              >
                <span className="font-semibold text-rose-600 dark:text-rose-400 font-mono">{label.decision}</span>
                {label.reason && <span className="text-muted-foreground break-words">{label.reason}</span>}
              </div>
            ))}
          </div>
        )}
        <div className="text-[10px] text-muted-foreground font-mono bg-muted/30 p-2 rounded-full overflow-x-auto whitespace-pre-wrap break-all">
          {JSON.stringify(tool.input_data ?? {}, null, 2)}
        </div>
        {tool.end_time && (
          <>
            <div className="text-xs font-medium text-foreground mt-1">{t('result')}</div>
            <div className="text-[10px] text-muted-foreground font-mono bg-muted/30 p-2 rounded-full overflow-x-auto whitespace-pre-wrap break-all max-h-[180px] overflow-y-auto">
              {typeof tool.output_data === 'object'
                ? JSON.stringify(tool.output_data, null, 2)
                : String(tool.output_data ?? tool.output_summary ?? '')}
            </div>
          </>
        )}
      </div>
    );
  }

  if (activeEvent?.type === 'message') {
    const m = activeEvent.data;
    return (
      <div className="flex flex-col gap-2">
        <div className="text-xs font-medium text-foreground">
          {m.role === 'user' ? t('userMessage') : t('assistantMessage')}
        </div>
        <div className="max-h-[200px] overflow-y-auto">
          <ReplayMessageBubble message={m} />
        </div>
      </div>
    );
  }

  return <p className="text-xs text-muted-foreground">{t('noPayload')}</p>;
}

export default ReplayInspector;
