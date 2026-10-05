'use client';

/**
 * [INPUT]
 * @/services/memory/commandCenter::MemoryCommandConflictItem (POS: 冲突数据契约)
 * lucide-react (POS: 矢量图标库，替代原生 emoji)
 * next-intl::useTranslations (POS: 双语 i18n 取词)
 *
 * [OUTPUT]
 * ConflictResolutionCard: 响应式双主题流光偏好仲裁卡片
 *
 * [POS]
 * 记忆冲突仲裁卡片组件。提供原认知与最新陈述的左右流光对比，支持一键采纳新事实、保留原事实或条件共存。
 */

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Sparkles, GitCompare, CheckCircle2, ShieldCheck, Split, Clock, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { MemoryCommandConflictItem } from '@/services/memory/commandCenter';

export interface ConflictResolutionCardProps {
  item: MemoryCommandConflictItem;
  onResolve?: (conflictId: string, action: 'keep_new' | 'keep_old' | 'coexist') => Promise<void>;
  resolving?: boolean;
}

export const ConflictResolutionCard = ({ item, onResolve, resolving = false }: ConflictResolutionCardProps) => {
  const t = useTranslations('memory');
  const [currentAction, setCurrentAction] = useState<string | null>(null);

  const isPending = item.status === 'pending' || item.status === 'active' || item.status === 'needs_review';

  const existingText = item.existing_content || (item.kind === 'pending_conflict' ? '' : item.description);
  const candidateText = item.candidate_content || '';

  const handleAction = async (action: 'keep_new' | 'keep_old' | 'coexist') => {
    if (!onResolve || resolving) {
      return;
    }
    setCurrentAction(action);
    try {
      await onResolve(item.id, action);
    } finally {
      setCurrentAction(null);
    }
  };

  return (
    <div
      className={cn(
        'group relative overflow-hidden rounded-xl p-4 transition-all duration-300',
        'border border-border/60 bg-gradient-to-br from-card/90 via-card/50 to-muted/20 backdrop-blur-md',
        'hover:border-primary/40 hover:shadow-lg hover:shadow-primary/5',
        isPending && 'border-amber-500/30 dark:border-amber-400/20',
      )}
    >
      {/* Top Banner: Status & Facet */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/40 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-500/10 text-amber-600 dark:bg-amber-400/10 dark:text-amber-400">
            <GitCompare className="h-3.5 w-3.5" />
          </div>
          <span className="text-xs font-semibold tracking-wide text-foreground">
            {item.title || t('commandCenter.conflictCardTitle')}
          </span>
          {isPending && (
            <span className="inline-flex items-center rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400">
              {t('commandCenter.conflictCardPending')}
            </span>
          )}
        </div>

        {item.created_at && (
          <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
            <Clock className="h-3 w-3" />
            <span>{new Date(item.created_at).toLocaleDateString()}</span>
          </div>
        )}
      </div>

      {/* Main Content: Comparison Grid (Responsive: column on mobile, 2-cols on desktop) */}
      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
        {/* Existing Fact */}
        <div className="flex flex-col justify-between rounded-lg border border-border/40 bg-muted/30 p-3 transition-colors group-hover:bg-muted/40">
          <div>
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
              <ShieldCheck className="h-3.5 w-3.5 text-blue-500" />
              <span>{t('commandCenter.conflictCardExisting')}</span>
            </div>
            <p className="mt-1.5 text-xs leading-relaxed text-foreground/90">{existingText}</p>
          </div>
        </div>

        {/* Candidate Fact */}
        {candidateText ? (
          <div className="flex flex-col justify-between rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 dark:border-amber-400/15 dark:bg-amber-400/5">
            <div>
              <div className="flex items-center gap-1.5 text-[11px] font-medium text-amber-600 dark:text-amber-400">
                <Sparkles className="h-3.5 w-3.5" />
                <span>{t('commandCenter.conflictCardCandidate')}</span>
              </div>
              <p className="mt-1.5 text-xs leading-relaxed text-foreground/90">{candidateText}</p>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center rounded-lg border border-dashed border-border/60 p-3 text-xs text-muted-foreground">
            <span>{t('commandCenter.conflictCardNoCandidate')}</span>
          </div>
        )}
      </div>

      {/* Action Buttons (Only shown for pending conflicts) */}
      {isPending && onResolve && (
        <div className="mt-4 flex flex-wrap items-center justify-end gap-2 pt-2 border-t border-border/30">
          <button
            type="button"
            onClick={() => handleAction('keep_old')}
            disabled={resolving}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all',
              'border border-border/60 bg-background/80 text-muted-foreground hover:bg-muted hover:text-foreground',
              'focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-50',
            )}
          >
            <ShieldCheck className="h-3.5 w-3.5" />
            <span>{t('commandCenter.conflictCardKeepOld')}</span>
          </button>

          <button
            type="button"
            onClick={() => handleAction('coexist')}
            disabled={resolving}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all',
              'border border-border/60 bg-background/80 text-muted-foreground hover:bg-muted hover:text-foreground',
              'focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-50',
            )}
          >
            <Split className="h-3.5 w-3.5" />
            <span>{t('commandCenter.conflictCardCoexist')}</span>
          </button>

          <button
            type="button"
            onClick={() => handleAction('keep_new')}
            disabled={resolving}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-white shadow-sm transition-all',
              'bg-gradient-to-r from-primary to-primary/85 hover:opacity-95',
              'focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-50',
            )}
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span>{t('commandCenter.conflictCardKeepNew')}</span>
            <ArrowRight className="h-3 w-3" />
          </button>
        </div>
      )}
    </div>
  );
};
