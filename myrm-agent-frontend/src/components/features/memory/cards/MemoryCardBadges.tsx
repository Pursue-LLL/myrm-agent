'use client';

/**
 * [INPUT]
 * @/store/memory::Memory, PendingMemory (POS: Frontend Memory Model)
 *
 * [OUTPUT]
 * MemoryCardBadges: Status badges shown in a memory card header (disabled, protected, exact fact, confidence, kind).
 *
 * [POS]
 * Presentational header badge group of MemoryCard; renders a fragment so the parent controls the layout.
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { AlertCircle, Lock, ShieldCheck, Sparkles, Tag } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { Memory, PendingMemory } from '@/store/memory';

const BADGE_BASE = 'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border';

interface MemoryCardBadgesProps {
  memory: PendingMemory | Memory;
  confirmed: Memory | null;
  isPending: boolean;
}

const ConfidenceBadge = ({ confidence }: { confidence: number }) => {
  const percent = Math.round(confidence * 100);
  if (percent >= 85) {
    return (
      <span
        className={cn(
          BADGE_BASE,
          'gap-0.5 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
        )}
      >
        <ShieldCheck size={10} />
        <span>{percent}%</span>
      </span>
    );
  }
  if (percent >= 60) {
    return (
      <span
        className={cn(BADGE_BASE, 'gap-0.5 bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20')}
      >
        <Sparkles size={10} />
        <span>{percent}%</span>
      </span>
    );
  }
  return (
    <span className={cn(BADGE_BASE, 'gap-0.5 bg-muted text-muted-foreground border-border/50')}>
      <AlertCircle size={10} />
      <span>{percent}%</span>
    </span>
  );
};

export const MemoryCardBadges = memo<MemoryCardBadgesProps>(({ memory, confirmed, isPending }) => {
  const t = useTranslations('memory');
  const exactIdentifiers = confirmed?.exact_identifiers ?? [];

  return (
    <>
      {confirmed?.status === 'disabled' && (
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">{t('disabled')}</span>
      )}
      {confirmed?.is_user_locked && (
        <span className="inline-flex" title={t('locked')}>
          <Lock size={12} className="text-amber-500" aria-label={t('locked')} />
        </span>
      )}
      {confirmed?.is_exact_fact && (
        <span
          className={cn(BADGE_BASE, 'gap-1 bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20')}
          title={
            exactIdentifiers.length > 0 ? `${t('exactFactHint')}: ${exactIdentifiers.join(', ')}` : t('exactFactHint')
          }
        >
          <Lock size={10} className="text-blue-500" />
          <span>{t('exactFact')}</span>
        </span>
      )}
      {isPending && 'confidence' in memory && memory.confidence !== undefined && memory.confidence !== null && (
        <ConfidenceBadge confidence={memory.confidence} />
      )}
      {isPending && 'kind' in memory && memory.kind && (
        <span className={cn(BADGE_BASE, 'gap-0.5 bg-primary/10 text-primary border-primary/20')}>
          <Tag size={9} />
          <span>{memory.kind}</span>
        </span>
      )}
    </>
  );
});

MemoryCardBadges.displayName = 'MemoryCardBadges';
