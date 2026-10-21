'use client';

/*
 * [INPUT]
 * - next-intl::useTranslations (POS: bilingual UI copy)
 * - React memo/useState (POS: local copy/send button state)
 * - services/contextHealth archive restore health DTOs
 *
 * [OUTPUT]
 * - PruningFooter: archive pruning footer with restore-block guidance controls.
 *
 * [POS]
 * Session analytics restore-guidance subview. Keeps range-specific restore UI
 * outside the high-level context health panel layout.
 */

import { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';
import { formatTokenCount } from './RoutingAnalyticsPanel';
import type {
  ArchiveRestoreBlockEvent,
  ArchiveRestoreContentFeature,
  ArchiveRestoreRangeHint,
  ContextHealth,
} from '@/services/contextHealth';

const RESTORE_REASON_LABEL_KEYS: Record<string, string> = {
  archive_restore_range_required: 'archiveRestoreRangeRequired',
  archive_refetch_path_budget_exceeded: 'archiveRefetchPathBudgetExceeded',
  archive_refetch_token_budget_exceeded: 'archiveRefetchTokenBudgetExceeded',
  archive_refetch_session_mismatch: 'archiveRefetchSessionMismatch',
  archive_restore_size_probe_failed: 'archiveRestoreSizeProbeFailed',
};

const RESTORE_HINT_REASON_LABEL_KEYS: Record<string, string> = {
  error_keyword: 'errorKeyword',
  section_heading: 'sectionHeading',
  code_block: 'codeBlock',
  table_range: 'tableRange',
  list_range: 'listRange',
  fallback_chunk: 'chunk',
  restore_map_range: 'range',
};

const RESTORE_CONTENT_FEATURE_LABEL_KEYS: Record<string, string> = {
  json_keys: 'jsonKeys',
  json_array: 'jsonArray',
  markdown_headings: 'markdownHeadings',
  code_blocks: 'codeBlocks',
  tables: 'tables',
  lists: 'lists',
  chunks: 'chunks',
};

interface PruningFooterProps {
  health: ContextHealth;
  message: string | null;
  sessionId: string;
}

export const PruningFooter = memo<PruningFooterProps>(({ health, message, sessionId }) => {
  const t = useTranslations('settings.sessionAnalytics');
  const router = useRouter();
  const activeChatId = useChatStore((state) => state.chatId);
  const [copiedArg, setCopiedArg] = useState('');
  const [copyFailedArg, setCopyFailedArg] = useState('');
  const [submittedArg, setSubmittedArg] = useState('');
  const [submitFailedArg, setSubmitFailedArg] = useState('');
  const failureKinds = Object.entries(health.pruning.offload_failure_kinds ?? {}).filter(([, count]) => count > 0);
  const deferredReasons = Object.entries(health.pruning.deferred_reasons ?? {}).filter(([, count]) => count > 0);
  const archiveDeferredReasons = Object.entries(health.pruning.archive_deferred_reasons ?? {}).filter(
    ([, count]) => count > 0,
  );
  const restoreBlocks = (health.pruning.archive_restore_block_events ?? []).slice(-2).reverse();
  const clipboardAvailable = typeof navigator !== 'undefined' && Boolean(navigator.clipboard?.writeText);
  const canSubmitRestore = activeChatId === sessionId;

  const copyRestoreArg = async (restoreArg: string): Promise<void> => {
    if (!restoreArg || !clipboardAvailable) {
      return;
    }
    try {
      await navigator.clipboard.writeText(restoreArg);
      setCopiedArg(restoreArg);
      setCopyFailedArg('');
    } catch {
      setCopyFailedArg(restoreArg);
    }
  };

  const submitRestoreArg = async (restoreArg: string): Promise<void> => {
    if (!restoreArg || !canSubmitRestore) {
      return;
    }
    try {
      await useChatStore
        .getState()
        .sendMessage(t('contextHealth.pruning.restorePrompt', { restoreArg }), undefined, undefined, undefined, [
          { type: 'archive_restore', restoreArg },
        ]);
      setSubmittedArg(restoreArg);
      setSubmitFailedArg('');
    } catch {
      setSubmitFailedArg(restoreArg);
    }
  };

  const openTargetSessionWithRestoreArg = (restoreArg: string): void => {
    if (!restoreArg) {
      return;
    }
    const encodedSessionId = encodeURIComponent(sessionId);
    const encodedRestoreArg = encodeURIComponent(restoreArg);
    router.push(`/${encodedSessionId}?restore_arg=${encodedRestoreArg}`);
  };

  const handleRestoreArg = async (restoreArg: string): Promise<void> => {
    if (canSubmitRestore) {
      await submitRestoreArg(restoreArg);
      return;
    }
    openTargetSessionWithRestoreArg(restoreArg);
  };

  if (
    !message &&
    failureKinds.length === 0 &&
    deferredReasons.length === 0 &&
    archiveDeferredReasons.length === 0 &&
    restoreBlocks.length === 0
  ) {
    return null;
  }

  return (
    <div className="space-y-3 border-t border-border/40 pt-3">
      {message ? <p className="text-xs text-muted-foreground">{message}</p> : null}
      {failureKinds.length > 0 ? (
        <div className="space-y-1.5">
          <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {t('contextHealth.pruning.failureKinds')}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {failureKinds.map(([kind, count]) => (
              <span
                key={kind}
                className={cn(
                  'rounded-full border border-amber-500/25 bg-amber-500/10 px-2 py-1 text-[11px] font-medium',
                  'text-amber-700 dark:text-amber-300',
                )}
              >
                {kind}: {count}
              </span>
            ))}
          </div>
        </div>
      ) : null}
      {deferredReasons.length > 0 ? (
        <div className="space-y-1.5">
          <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {t('contextHealth.pruning.deferredReasons')}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {deferredReasons.map(([reason, count]) => (
              <span
                key={reason}
                className={cn(
                  'rounded-full border border-sky-500/25 bg-sky-500/10 px-2 py-1 text-[11px] font-medium',
                  'text-sky-700 dark:text-sky-300',
                )}
              >
                {reason}: {count}
              </span>
            ))}
          </div>
        </div>
      ) : null}
      {archiveDeferredReasons.length > 0 ? (
        <div className="space-y-1.5">
          <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {t('contextHealth.pruning.archiveDeferredReasons')}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {archiveDeferredReasons.map(([reason, count]) => (
              <span
                key={reason}
                className={cn(
                  'rounded-full border border-indigo-500/25 bg-indigo-500/10 px-2 py-1 text-[11px] font-medium',
                  'text-indigo-700 dark:text-indigo-300',
                )}
              >
                {reason}: {count}
              </span>
            ))}
          </div>
          {health.pruning.archive_deferred_soft_trimmed_count > 0 ? (
            <p className="text-[11px] text-muted-foreground">
              {t('contextHealth.pruning.archiveDeferredSoftTrimmed', {
                count: health.pruning.archive_deferred_soft_trimmed_count,
              })}
            </p>
          ) : null}
        </div>
      ) : null}
      {restoreBlocks.length > 0 ? (
        <div className="space-y-2">
          <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {t('contextHealth.pruning.recentRestoreBlocks')}
          </p>
          {!canSubmitRestore ? (
            <p className="break-all rounded-full border border-amber-500/25 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-700 dark:text-amber-300">
              {t('contextHealth.pruning.restoreActiveSessionRequired', { sessionId })}
            </p>
          ) : null}
          {restoreBlocks.map((event, index) => {
            const restoreArg = getPrimaryRestoreArg(event);
            const rangeHints = getRestoreRangeHints(event);
            const contentFeatures = event.content_features?.filter((feature) => feature.count > 0).slice(0, 6) ?? [];
            return (
              <div
                key={`${event.timestamp}-${event.archive_path}-${event.reason}-${index}`}
                className={cn(
                  'space-y-2 rounded-lg border border-border/50 bg-muted/20 p-2.5 text-xs',
                  event.severity === 'critical'
                    ? 'border-rose-500/25 bg-rose-500/5'
                    : 'border-amber-500/20 bg-amber-500/5',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-foreground">{getRestoreReasonLabel(event, t)}</span>
                  <span className="tabular-nums text-muted-foreground">{formatTokenCount(event.estimated_tokens)}</span>
                </div>
                <p className="break-all text-muted-foreground">{event.archive_path}</p>
                {contentFeatures.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {contentFeatures.map((feature) => (
                      <span
                        key={`${feature.feature_type}-${feature.count}-${feature.values.join(',')}`}
                        className="rounded-full border border-sky-500/20 bg-sky-500/10 px-2 py-1 text-[11px] text-sky-700 dark:text-sky-300"
                      >
                        {getContentFeatureText(feature, t)}
                      </span>
                    ))}
                  </div>
                ) : null}
                {rangeHints.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {rangeHints.map((hint) => (
                      <button
                        key={hint.range_arg}
                        type="button"
                        onClick={() => {
                          void handleRestoreArg(hint.range_arg);
                        }}
                        className={cn(
                          'inline-flex min-h-8 max-w-full flex-col items-start rounded-full border px-2 py-1 text-left',
                          'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 transition-colors hover:bg-emerald-500/15',
                          'dark:text-emerald-300',
                          !canSubmitRestore &&
                            'border-sky-500/25 bg-sky-500/10 text-sky-700 hover:bg-sky-500/15 dark:text-sky-300',
                        )}
                      >
                        <span className="text-[11px] font-medium">
                          {getRangeHintLabel(hint, t)} · {formatRangeLineSpan(hint)}
                        </span>
                        <span className="max-w-full break-all font-mono text-[11px] text-foreground">
                          {hint.range_arg}
                        </span>
                      </button>
                    ))}
                  </div>
                ) : null}
                {event.guidance_source ? (
                  <p className="text-[11px] text-muted-foreground">
                    {t('contextHealth.pruning.restoreGuidance')}: {event.guidance_source}
                    {event.fallback_reason
                      ? ` / ${t('contextHealth.pruning.restoreFallback')}: ${event.fallback_reason}`
                      : ''}
                  </p>
                ) : null}
                {event.suggested_action ? (
                  <p className="text-amber-700 dark:text-amber-300">{event.suggested_action}</p>
                ) : null}
                {restoreArg ? (
                  <div className="flex flex-wrap gap-1.5">
                    <button
                      type="button"
                      onClick={() => {
                        void handleRestoreArg(restoreArg);
                      }}
                      className={cn(
                        'inline-flex min-h-8 items-center rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5',
                        'text-[11px] font-medium text-emerald-700 transition-colors hover:bg-emerald-500/15',
                        'dark:text-emerald-300',
                        !canSubmitRestore &&
                          'border-sky-500/30 bg-sky-500/10 text-sky-700 hover:bg-sky-500/15 dark:text-sky-300',
                      )}
                    >
                      {getRestoreButtonLabel({ restoreArg, submittedArg, submitFailedArg, canSubmitRestore, t })}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        void copyRestoreArg(restoreArg);
                      }}
                      disabled={!clipboardAvailable}
                      className={cn(
                        'inline-flex min-h-8 items-center rounded-full border border-border/60 bg-background/80 px-2.5',
                        'text-[11px] font-medium text-foreground transition-colors hover:bg-accent',
                        !clipboardAvailable && 'cursor-not-allowed opacity-60 hover:bg-background/80',
                      )}
                    >
                      {getCopyButtonLabel({
                        restoreArg,
                        copiedArg,
                        copyFailedArg,
                        clipboardAvailable,
                        t,
                      })}
                    </button>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
});
PruningFooter.displayName = 'PruningFooter';

function getRestoreReasonLabel(event: ArchiveRestoreBlockEvent, t: ReturnType<typeof useTranslations>): string {
  const labelKey = RESTORE_REASON_LABEL_KEYS[event.reason_label_key || event.reason] ?? 'unknown';
  return t(`contextHealth.pruning.restoreReasons.${labelKey}`);
}

function getPrimaryRestoreArg(event: ArchiveRestoreBlockEvent): string {
  return event.primary_restore_arg || event.recommended_ranges?.[0] || '';
}

function getRestoreRangeHints(event: ArchiveRestoreBlockEvent): ArchiveRestoreRangeHint[] {
  const hints = event.restore_range_hints?.filter((hint) => hint.range_arg).slice(0, 3) ?? [];
  if (hints.length > 0) {
    return hints;
  }
  return (event.recommended_ranges ?? [])
    .filter(Boolean)
    .slice(0, 3)
    .map((range) => buildFallbackRangeHint(range));
}

function buildFallbackRangeHint(range: string): ArchiveRestoreRangeHint {
  const [, lineSpan = ''] = range.match(/:(\d+-\d+)$/) ?? [];
  const [startLine, endLine] = lineSpan.split('-').map((value) => Number.parseInt(value, 10));
  const safeStart = Number.isFinite(startLine) ? startLine : 0;
  const safeEnd = Number.isFinite(endLine) ? endLine : safeStart;
  return {
    range_arg: range,
    reason: 'fallback_chunk',
    start_line: safeStart,
    end_line: safeEnd,
    line: safeStart,
  };
}

function getRangeHintLabel(hint: ArchiveRestoreRangeHint, t: ReturnType<typeof useTranslations>): string {
  const labelKey = RESTORE_HINT_REASON_LABEL_KEYS[hint.reason] ?? 'range';
  return t(`contextHealth.pruning.restoreHintReasons.${labelKey}`);
}

function formatRangeLineSpan(hint: ArchiveRestoreRangeHint): string {
  if (hint.start_line <= 0 || hint.end_line <= 0) {
    return '-';
  }
  return `${hint.start_line}-${hint.end_line}`;
}

function getContentFeatureText(feature: ArchiveRestoreContentFeature, t: ReturnType<typeof useTranslations>): string {
  const label = getContentFeatureLabel(feature, t);
  if (feature.feature_type === 'json_keys' && feature.values.length > 0) {
    return `${label}: ${feature.values.join(', ')}`;
  }
  return `${label}: ${feature.count}`;
}

function getContentFeatureLabel(feature: ArchiveRestoreContentFeature, t: ReturnType<typeof useTranslations>): string {
  const labelKey = RESTORE_CONTENT_FEATURE_LABEL_KEYS[feature.feature_type] ?? 'unknown';
  return t(`contextHealth.pruning.contentFeatures.${labelKey}`);
}

function getCopyButtonLabel({
  restoreArg,
  copiedArg,
  copyFailedArg,
  clipboardAvailable,
  t,
}: {
  restoreArg: string;
  copiedArg: string;
  copyFailedArg: string;
  clipboardAvailable: boolean;
  t: ReturnType<typeof useTranslations>;
}): string {
  if (!clipboardAvailable) {
    return t('contextHealth.pruning.copyRestoreArgUnavailable');
  }
  if (copyFailedArg === restoreArg) {
    return t('contextHealth.pruning.copyRestoreArgFailed');
  }
  if (copiedArg === restoreArg) {
    return t('contextHealth.pruning.restoreArgCopied');
  }
  return t('contextHealth.pruning.copyRestoreArg');
}

function getRestoreButtonLabel({
  restoreArg,
  submittedArg,
  submitFailedArg,
  canSubmitRestore,
  t,
}: {
  restoreArg: string;
  submittedArg: string;
  submitFailedArg: string;
  canSubmitRestore: boolean;
  t: ReturnType<typeof useTranslations>;
}): string {
  if (!canSubmitRestore) {
    return t('contextHealth.pruning.restoreRangeRequiresActiveSession');
  }
  if (submitFailedArg === restoreArg) {
    return t('contextHealth.pruning.restoreRangeFailed');
  }
  if (submittedArg === restoreArg) {
    return t('contextHealth.pruning.restoreRangeSubmitted');
  }
  return t('contextHealth.pruning.restoreRange');
}
