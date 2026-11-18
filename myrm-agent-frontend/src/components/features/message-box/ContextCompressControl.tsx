'use client';

/**
 * [INPUT]
 * - store/useChatStore::refreshCompactionState (POS: Chat state management store.)
 * - services/contextCompaction::compactChat (POS: Context compaction service.)
 * - lib/constants/compact-focus-topic::COMPACT_FOCUS_TOPIC_MAX_LENGTH (POS: Longest focus topic the server accepts.)
 * - ./contextUsageFormat::formatTokens (POS: Compact K / M token count.)
 *
 * [OUTPUT]
 * - ContextCompressControl: focus-topic input, compress button and outcome line of a manual compaction.
 *
 * [POS]
 * Manual compaction control of the strategy panel. Owns the in-flight, result and error state of one request.
 * A compaction that freed tokens goes to the store, whose refresh counter is what makes the indicator read the
 * strategy health again.
 */

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import useChatStore from '@/store/useChatStore';
import { compactChat } from '@/services/contextCompaction';
import { COMPACT_FOCUS_TOPIC_MAX_LENGTH } from '@/lib/constants/compact-focus-topic';
import { formatTokens } from './contextUsageFormat';

interface ContextCompressControlProps {
  chatId: string | null;
  usagePercent: number;
}

export function ContextCompressControl({ chatId, usagePercent }: ContextCompressControlProps) {
  const t = useTranslations('chat.contextUsage.strategy');
  const [compacting, setCompacting] = useState(false);
  const [compactResult, setCompactResult] = useState<string | null>(null);
  const [compactError, setCompactError] = useState<string | null>(null);
  const [focusTopic, setFocusTopic] = useState('');

  const canCompress = !!chatId && usagePercent >= 30 && !compacting;

  const handleCompress = useCallback(async () => {
    if (!chatId || compacting) {
      return;
    }
    setCompacting(true);
    setCompactResult(null);
    setCompactError(null);
    try {
      const result = await compactChat(chatId, focusTopic.trim() || undefined);
      if (result.compacted) {
        setCompactResult(t('compressSuccess', { tokens: formatTokens(result.tokens_saved) }));
        await useChatStore.getState().refreshCompactionState(chatId, {
          tokensSaved: result.tokens_saved,
          snapshotPath: result.backup_path ?? undefined,
        });
      } else {
        setCompactResult(t('compressNotNeeded'));
      }
    } catch (err) {
      setCompactError(err instanceof Error ? err.message : t('compressError'));
    } finally {
      setCompacting(false);
    }
  }, [chatId, compacting, focusTopic, t]);

  return (
    <>
      <input
        type="text"
        value={focusTopic}
        onChange={(event) => setFocusTopic(event.target.value)}
        maxLength={COMPACT_FOCUS_TOPIC_MAX_LENGTH}
        placeholder={t('focusHintPlaceholder')}
        className="w-full text-[11px] px-2 py-1.5 rounded-md border border-border/60 bg-background"
      />
      <button
        type="button"
        disabled={!canCompress}
        onClick={handleCompress}
        className={`w-full text-[11px] font-medium py-1.5 px-2 rounded-md transition-colors ${
          canCompress
            ? 'bg-primary-dark/10 text-primary-dark hover:bg-primary-dark/20 dark:bg-primary-light/10 dark:text-primary-light dark:hover:bg-primary-light/20'
            : 'bg-muted text-muted-foreground cursor-not-allowed'
        }`}
      >
        {compacting ? t('compressing') : t('compressContext')}
      </button>

      {compactResult && <span className="text-[10px] text-emerald-600 dark:text-emerald-400">{compactResult}</span>}
      {compactError && <span className="text-[10px] text-rose-600 dark:text-rose-400">{compactError}</span>}
    </>
  );
}
