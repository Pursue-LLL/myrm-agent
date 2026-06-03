/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线)
 * - @/store/chat/types::ArchiveRestoreAction (POS: Chat state and SSE event type definitions)
 *
 * [OUTPUT]
 * - ArchiveRestoreStepAction: inline restore-and-continue control for archive_restore_blocked progress steps.
 *
 * [POS]
 * Progress-step archive restore action view. Bridges a typed restore action array into direct send,
 * busy-state input preparation, and retry-safe pending action restoration.
 */

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import useChatStore from '@/store/useChatStore';
import type { ArchiveRestoreAction, ArchiveRestoreBlockPayload, ArchiveRestoreRangeHint } from '@/store/chat/types';
import { cn } from '@/lib/utils/classnameUtils';

type ArchiveRestoreStepActionProps = {
  actions: ArchiveRestoreAction[];
  block?: ArchiveRestoreBlockPayload;
};

const archiveRestoreKey = (actions: ArchiveRestoreAction[]): string =>
  actions.map((action) => action.restoreArg).join('\n');

const formatNumber = (value: number): string => new Intl.NumberFormat().format(value);

const humanizeToken = (value: string | undefined): string | undefined => {
  const normalized = value?.trim();
  if (!normalized) {
    return undefined;
  }
  return normalized
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
};

const formatRangeHint = (hint: ArchiveRestoreRangeHint | undefined): string | undefined =>
  humanizeToken(hint?.label) ?? humanizeToken(hint?.reason);

const formatContentFeature = (feature: NonNullable<ArchiveRestoreBlockPayload['content_features']>[number]): string => {
  const label = humanizeToken(feature.feature_type) ?? feature.feature_type;
  const values = feature.values.slice(0, 3).join(', ');
  const countLabel = feature.count > 0 ? ` (${formatNumber(feature.count)})` : '';
  return values ? `${label}${countLabel}: ${values}` : `${label}${countLabel}`;
};

const focusMessageInput = () => {
  window.setTimeout(() => {
    const inputElement = document.querySelector('textarea');
    if (inputElement instanceof HTMLTextAreaElement) {
      inputElement.focus();
      inputElement.setSelectionRange(inputElement.value.length, inputElement.value.length);
    }
  }, 50);
};

export const ArchiveRestoreStepAction = ({ actions, block }: ArchiveRestoreStepActionProps) => {
  const t = useTranslations('progressSteps');
  const [submittingKey, setSubmittingKey] = useState<string | null>(null);
  const restoreArg = actions.map((action) => action.restoreArg).join(', ');
  const restoreKey = archiveRestoreKey(actions);
  const rangeHintsByArg = new Map((block?.restore_range_hints ?? []).map((hint) => [hint.range_arg, hint]));
  const details = [
    block?.estimated_tokens !== undefined
      ? t('archiveRestoreMetadataTokens', { tokens: formatNumber(block.estimated_tokens) })
      : undefined,
    block?.reason
      ? t('archiveRestoreMetadataReason', { reason: humanizeToken(block.reason) ?? block.reason })
      : undefined,
    block?.guidance_source
      ? t('archiveRestoreMetadataGuidance', {
          source: humanizeToken(block.guidance_source) ?? block.guidance_source,
        })
      : undefined,
    block?.fallback_reason
      ? t('archiveRestoreMetadataFallback', {
          reason: humanizeToken(block.fallback_reason) ?? block.fallback_reason,
        })
      : undefined,
    block?.archive_path ? t('archiveRestoreMetadataArchive', { path: block.archive_path }) : undefined,
  ].filter((detail): detail is string => Boolean(detail));
  const featureSummary = block?.content_features?.slice(0, 2).map(formatContentFeature).filter(Boolean).join('; ');

  const handleClick = async () => {
    if (actions.length === 0) {
      return;
    }
    const prompt = t('archiveRestorePrompt', { restoreArg });
    const store = useChatStore.getState();

    if (store.loading) {
      store.setPendingArchiveRestoreActions(actions);
      store.setInputMessage(prompt);
      focusMessageInput();
      const { toast } = await import('@/lib/utils/toast');
      toast.info(t('archiveRestorePrepared'), { duration: 4000 });
      return;
    }

    setSubmittingKey(restoreKey);
    try {
      await store.sendMessage(prompt, undefined, undefined, undefined, actions);
    } catch {
      store.setPendingArchiveRestoreActions(actions);
      store.setInputMessage(prompt);
      focusMessageInput();
      const { toast } = await import('@/lib/utils/toast');
      toast.warning(t('archiveRestoreFailed'), { duration: 5000 });
    } finally {
      setSubmittingKey(null);
    }
  };

  return (
    <div
      className={cn(
        'mt-2 space-y-2 rounded-lg border px-3 py-2.5 text-xs',
        'border-primary/25 bg-primary/10 text-foreground',
      )}
      onClick={(event) => event.stopPropagation()}
    >
      <p className="leading-relaxed text-foreground/85">
        {t('archiveRestoreCardDescription', { count: actions.length })}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {actions.map((action) => {
          const rangeHint = formatRangeHint(rangeHintsByArg.get(action.restoreArg));
          return (
            <span
              key={action.restoreArg}
              className={cn(
                'max-w-full rounded-full border border-primary/20 bg-background/70 px-2 py-1',
                'text-[11px] text-foreground',
              )}
            >
              <span className="break-all font-mono">{action.restoreArg}</span>
              {rangeHint && (
                <span className="mt-0.5 block break-words text-foreground/65">
                  {t('archiveRestoreRangeReason', { reason: rangeHint })}
                </span>
              )}
            </span>
          );
        })}
      </div>
      {(details.length > 0 || featureSummary) && (
        <div className="space-y-1 rounded-full border border-primary/15 bg-background/45 px-2.5 py-2 text-[11px] text-foreground/75">
          {details.map((detail) => (
            <p key={detail} className="break-words leading-relaxed">
              {detail}
            </p>
          ))}
          {featureSummary && (
            <p className="break-words leading-relaxed">
              {t('archiveRestoreContentFeatures', { features: featureSummary })}
            </p>
          )}
        </div>
      )}
      <button
        type="button"
        disabled={submittingKey === restoreKey}
        onClick={(event) => {
          event.stopPropagation();
          void handleClick();
        }}
        className={cn(
          'inline-flex min-h-8 max-w-full items-center justify-center rounded-full border px-3 py-1.5',
          'border-primary/30 bg-primary text-xs font-medium text-primary-foreground transition-colors',
          'hover:bg-primary-hover disabled:cursor-wait disabled:opacity-70',
        )}
      >
        {submittingKey === restoreKey
          ? t('archiveRestoreSubmitting')
          : t('archiveRestoreButton', { count: actions.length })}
      </button>
    </div>
  );
};
