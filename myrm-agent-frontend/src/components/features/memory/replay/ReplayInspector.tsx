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
import ModelViewportView from '@/components/features/memory/replay/ModelViewportView';
import { IconGitBranch, IconLoader } from '@/components/features/icons/PremiumIcons';

interface ReplayInspectorProps {
  activeEvent: ReplayEvent | null;
  onForkFromCurrent?: () => void;
  isForking?: boolean;
}

function ReplayInspector({ activeEvent, onForkFromCurrent, isForking = false }: ReplayInspectorProps) {
  const t = useTranslations('settings.sessionAnalytics.replay');

  const renderForkButton = () => {
    if (!onForkFromCurrent) return null;
    return (
      <div className="mt-3 pt-2.5 border-t border-border/30 flex items-center justify-between gap-2">
        <span className="text-[10px] text-muted-foreground">{t('forkBranchHint')}</span>
        <button
          type="button"
          onClick={onForkFromCurrent}
          disabled={isForking}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors shrink-0"
        >
          {isForking ? (
            <>
              <IconLoader className="h-3 w-3 animate-spin" />
              <span>{t('forkingBranch')}</span>
            </>
          ) : (
            <>
              <IconGitBranch className="h-3.5 w-3.5" />
              <span>{t('forkFromThisStep')}</span>
            </>
          )}
        </button>
      </div>
    );
  };

  if (activeEvent?.type === 'error') {
    return (
      <div className="flex flex-col gap-2">
        <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-xs text-rose-600 dark:text-rose-400 font-mono break-all whitespace-pre-wrap">
          {activeEvent.data.error}
        </div>
        {renderForkButton()}
      </div>
    );
  }

  if (activeEvent?.type === 'tool_end' && !activeEvent.data.success) {
    return (
      <div className="flex flex-col gap-2">
        <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-xs text-rose-600 dark:text-rose-400 font-mono break-all whitespace-pre-wrap">
          {activeEvent.data.error ?? t('toolFailed')}
        </div>
        {renderForkButton()}
      </div>
    );
  }

  if (activeEvent?.type === 'human_feedback') {
    const fb = activeEvent.data;
    return (
      <div className="flex flex-col gap-2">
        <div className="text-xs font-medium text-foreground">{t('humanFeedbackTitle')}</div>
        <div className="text-[10px] text-muted-foreground font-mono bg-muted/30 p-2 rounded-xl whitespace-pre-wrap break-all">
          {JSON.stringify(fb, null, 2)}
        </div>
        {renderForkButton()}
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
        <div className="text-[10px] text-muted-foreground font-mono bg-muted/30 p-2 rounded-xl whitespace-pre-wrap break-all max-h-[200px] overflow-y-auto">
          {me.summary}
        </div>
        {renderForkButton()}
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
          <ModelViewportView promptPreview={lc.prompt_preview} />
        )}
        <div className="text-[10px] text-muted-foreground font-mono bg-muted/30 p-2 rounded-xl whitespace-pre-wrap break-all">
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
        {renderForkButton()}
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
            <div className="text-[10px] text-muted-foreground font-mono bg-muted/30 p-2 rounded-xl overflow-x-auto whitespace-pre-wrap break-all max-h-[180px] overflow-y-auto">
              {typeof tool.output_data === 'object'
                ? JSON.stringify(tool.output_data, null, 2)
                : String(tool.output_data ?? tool.output_summary ?? '')}
            </div>
          </>
        )}
        {renderForkButton()}
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
        {renderForkButton()}
      </div>
    );
  }

  return <p className="text-xs text-muted-foreground">{t('noPayload')}</p>;
}

export default ReplayInspector;
