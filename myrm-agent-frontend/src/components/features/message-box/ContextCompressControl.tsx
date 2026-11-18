'use client';

/**
 * [INPUT]
 * - services/contextCompaction::runManualCompaction, describeCompactSkip, COMPACT_FAILED_NOTICE, CompactNotice (POS: Manual compaction and the wording of a compaction that did not run.)
 * - lib/constants/compact-focus-topic::COMPACT_FOCUS_TOPIC_MAX_LENGTH (POS: Longest focus topic the server accepts.)
 * - ./contextUsageFormat::formatTokens (POS: Compact K / M token count.)
 *
 * [OUTPUT]
 * - ContextCompressControl: focus-topic input, compress button and outcome line of a manual compaction.
 *
 * [POS]
 * Manual compaction control of the strategy panel. Owns the in-flight, typed-topic and outcome state of one request.
 * The compaction reaches the store inside `runManualCompaction`; the store's refresh counter is what makes the indicator
 * read the strategy health again, while this control stays mounted and keeps its state.
 */

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  COMPACT_FAILED_NOTICE,
  describeCompactSkip,
  runManualCompaction,
  type CompactNotice,
} from '@/services/contextCompaction';
import { COMPACT_FOCUS_TOPIC_MAX_LENGTH } from '@/lib/constants/compact-focus-topic';
import { formatTokens } from './contextUsageFormat';

interface ContextCompressControlProps {
  chatId: string | null;
  usagePercent: number;
}

interface Outcome {
  tone: 'success' | CompactNotice['severity'];
  text: string;
}

const OUTCOME_TONE_CLASS: Record<Outcome['tone'], string> = {
  success: 'text-emerald-600 dark:text-emerald-400',
  info: 'text-muted-foreground',
  warning: 'text-amber-600 dark:text-amber-400',
  error: 'text-rose-600 dark:text-rose-400',
};

export function ContextCompressControl({ chatId, usagePercent }: ContextCompressControlProps) {
  const t = useTranslations('chat.contextUsage.strategy');
  // The notices carry absolute locale keys, shared with the input box and the `/compact` command.
  const tNotice = useTranslations();
  const [compacting, setCompacting] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [focusTopic, setFocusTopic] = useState('');

  const canCompress = !!chatId && usagePercent >= 30 && !compacting;

  const handleCompress = useCallback(async () => {
    if (!chatId || compacting) {
      return;
    }
    setCompacting(true);
    setOutcome(null);
    try {
      const result = await runManualCompaction(chatId, focusTopic.trim() || undefined);
      if (result.compacted) {
        setOutcome({ tone: 'success', text: t('compressSuccess', { tokens: formatTokens(result.tokens_saved) }) });
      } else {
        const { messageKey, severity } = describeCompactSkip(result.reason);
        setOutcome({ tone: severity, text: tNotice(messageKey) });
      }
    } catch {
      setOutcome({ tone: 'error', text: tNotice(COMPACT_FAILED_NOTICE.messageKey) });
    } finally {
      setCompacting(false);
    }
  }, [chatId, compacting, focusTopic, t, tNotice]);

  return (
    <>
      <input
        type="text"
        value={focusTopic}
        onChange={(event) => setFocusTopic(event.target.value)}
        maxLength={COMPACT_FOCUS_TOPIC_MAX_LENGTH}
        placeholder={t('focusHintPlaceholder')}
        className="w-full text-[11px] px-2 py-1.5 rounded-lg border border-border/60 bg-background"
      />
      <button
        type="button"
        disabled={!canCompress}
        onClick={handleCompress}
        className={`w-full text-[11px] font-medium py-1.5 px-2 rounded-lg transition-colors ${
          canCompress
            ? 'bg-primary-dark/10 text-primary-dark hover:bg-primary-dark/20 dark:bg-primary-light/10 dark:text-primary-light dark:hover:bg-primary-light/20'
            : 'bg-muted text-muted-foreground cursor-not-allowed'
        }`}
      >
        {compacting ? t('compressing') : t('compressContext')}
      </button>

      {outcome && <span className={`text-[10px] ${OUTCOME_TONE_CLASS[outcome.tone]}`}>{outcome.text}</span>}
    </>
  );
}
