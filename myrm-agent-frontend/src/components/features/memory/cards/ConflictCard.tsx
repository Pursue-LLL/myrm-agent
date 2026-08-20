'use client';

import { memo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { AlertTriangle, ArrowRight, Check, GitMerge, RotateCcw, Trash2, Clock, Pencil } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { PendingMemory, ConflictResolution } from '@/store/memory';
import MemoryTypeIcon from './MemoryTypeIcon';

interface ConflictCardProps {
  conflict: PendingMemory;
  onResolve: (id: string, resolution: ConflictResolution, mergedContent?: string) => Promise<void>;
  className?: string;
}

const formatDate = (dateString: string) => {
  const date = new Date(dateString);
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const formatTimeRemaining = (autoResolveAt: string, t: ReturnType<typeof useTranslations<'memory'>>): string => {
  const diff = new Date(autoResolveAt).getTime() - Date.now();
  if (diff <= 0) {
    return t('conflict.autoResolveSoon', { defaultMessage: '即将自动解决' });
  }
  const minutes = Math.floor(diff / (1000 * 60));
  if (minutes < 60) {
    return t('conflict.autoResolveInMinutes', { minutes, defaultMessage: '{minutes}分钟后自动保留旧记忆' });
  }
  const hours = Math.floor(minutes / 60);
  if (hours >= 24) {
    const days = Math.floor(hours / 24);
    return t('conflict.autoResolveInDays', { days, defaultMessage: '{days}天后自动保留旧记忆' });
  }
  return t('conflict.autoResolveInHours', { hours, defaultMessage: '{hours}小时后自动保留旧记忆' });
};

const ConflictCard = memo<ConflictCardProps>(({ conflict, onResolve, className }) => {
  const t = useTranslations('memory');
  const [resolving, setResolving] = useState(false);
  const [showMergeEditor, setShowMergeEditor] = useState(false);
  const [mergedContent, setMergedContent] = useState((conflict.extra_data?.merge_suggestion as string) || '');

  const handleResolve = useCallback(
    async (resolution: ConflictResolution, content?: string) => {
      setResolving(true);
      try {
        await onResolve(conflict.id, resolution, content);
      } finally {
        setResolving(false);
      }
    },
    [conflict.id, onResolve],
  );

  const importancePercent = conflict.conflict_importance ? Math.round(conflict.conflict_importance * 100) : null;

  // High-risk conflicts (server keeps auto_resolve_at None) never auto-resolve.
  // isHighRisk is the authoritative signal from the server; the badge follows it
  // so the UI can never show "high risk" while a 72h countdown is running.
  const isHighRisk = !conflict.conflict_auto_resolve_at;
  const showHighRiskBadge = isHighRisk && importancePercent !== null;

  return (
    <div
      className={cn(
        'relative rounded-xl border-2 bg-card',
        'transition-all duration-200 hover:shadow-md',
        isHighRisk
          ? 'border-red-500/50 hover:shadow-red-500/10 hover:border-red-500/70'
          : 'border-amber-500/40 hover:shadow-amber-500/10 hover:border-amber-500/60',
        resolving && 'opacity-60 pointer-events-none',
        className,
      )}
    >
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2 px-4 pt-4 pb-2">
        <div
          className={cn(
            'flex items-center justify-center h-7 w-7 rounded-lg',
            isHighRisk ? 'bg-red-600/15' : 'bg-amber-500/15',
          )}
        >
          <AlertTriangle size={16} className={isHighRisk ? 'text-red-500' : 'text-amber-500'} />
        </div>
        <span
          className={cn(
            'text-xs font-semibold uppercase tracking-wide',
            isHighRisk ? 'text-red-600 dark:text-red-400' : 'text-amber-600 dark:text-amber-400',
          )}
        >
          {t('conflict.title', { defaultMessage: '记忆冲突' })}
        </span>
        <MemoryTypeIcon type={conflict.memory_type} size={14} showBackground />
        <div className="ml-auto flex items-center gap-2 text-[11px] text-muted-foreground">
          {importancePercent !== null && (
            <span
              className={cn(
                'px-1.5 py-0.5 rounded-md font-medium',
                showHighRiskBadge
                  ? 'bg-red-600/15 text-red-600 dark:text-red-400 border border-red-500/30'
                  : importancePercent >= 70
                    ? 'bg-red-500/10 text-red-600 dark:text-red-400'
                    : 'bg-muted text-muted-foreground',
              )}
            >
              {showHighRiskBadge ? `${t('conflict.highRisk', { defaultMessage: '高风险' })} · ` : ''}
              {t('conflict.importance', { defaultMessage: '重要度' })} {importancePercent}%
            </span>
          )}
          {isHighRisk ? (
            <span className="flex items-center gap-1 font-medium text-red-600 dark:text-red-400">
              <Clock size={11} />
              {t('conflict.autoResolveNever', { defaultMessage: '不会自动解决 · 需手动确认' })}
            </span>
          ) : (
            conflict.conflict_auto_resolve_at && (
              <span className="flex items-center gap-1 text-muted-foreground/70">
                <Clock size={11} />
                {formatTimeRemaining(conflict.conflict_auto_resolve_at, t)}
              </span>
            )
          )}
        </div>
      </div>

      {/* Conflict body: old vs new */}
      <div className="px-4 pb-3 space-y-3">
        {/* Old content */}
        <div className="rounded-lg border border-border/60 bg-muted/30 p-3">
          <div className="flex items-center gap-1.5 mb-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              {t('conflict.currentMemory', { defaultMessage: '当前记忆' })}
            </span>
          </div>
          <p className="text-sm text-foreground/80 leading-relaxed line-clamp-4">
            {conflict.conflict_old_content || t('conflict.unknown', { defaultMessage: '（内容不可用）' })}
          </p>
        </div>

        <div className="flex justify-center">
          <ArrowRight size={16} className="text-amber-500/60 rotate-90" />
        </div>

        {/* New content */}
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
          <div className="flex items-center gap-1.5 mb-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400">
              {t('conflict.newMemory', { defaultMessage: '新提取内容' })}
            </span>
          </div>
          <p className="text-sm text-foreground leading-relaxed line-clamp-4">{conflict.content}</p>
        </div>

        {/* Merge editor */}
        {showMergeEditor && (
          <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 space-y-2">
            <div className="flex items-center gap-1.5">
              <GitMerge size={12} className="text-primary" />
              <span className="text-[10px] font-semibold uppercase tracking-wider text-primary">
                {t('conflict.mergedContent', { defaultMessage: '合并内容' })}
              </span>
            </div>
            <textarea
              value={mergedContent}
              onChange={(e) => setMergedContent(e.target.value)}
              className={cn(
                'w-full min-h-[80px] rounded-md border border-border/60 bg-background',
                'px-3 py-2 text-sm text-foreground',
                'focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50',
                'resize-y',
              )}
              placeholder={t('conflict.mergePlaceholder', { defaultMessage: '编辑合并后的记忆内容...' })}
            />
          </div>
        )}

        {/* Metadata */}
        <div className="flex items-center gap-3 text-[11px] text-muted-foreground/70">
          <span>{formatDate(conflict.created_at)}</span>
          {conflict.conflict_accuracy_score !== undefined && conflict.conflict_accuracy_score !== null && (
            <span>
              {t('conflict.accuracy', { defaultMessage: '准确度' })}:{' '}
              {Math.round(conflict.conflict_accuracy_score * 100)}%
            </span>
          )}
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex flex-wrap items-center gap-2 px-4 pb-4 pt-2 border-t border-border/50">
        <button
          onClick={() => handleResolve('keep_old')}
          disabled={resolving}
          className={cn(
            'flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg',
            'text-xs font-medium transition-all duration-200',
            'border border-border/50 hover:border-border',
            'text-muted-foreground hover:text-foreground hover:bg-accent/50',
          )}
        >
          <RotateCcw size={13} />
          {t('conflict.keepOld', { defaultMessage: '保留旧的' })}
        </button>

        <button
          onClick={() => handleResolve('keep_new')}
          disabled={resolving}
          className={cn(
            'flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg',
            'text-xs font-medium transition-all duration-200',
            'bg-primary/10 hover:bg-primary/20',
            'text-primary border border-primary/20 hover:border-primary/40',
          )}
        >
          <Check size={13} />
          {t('conflict.keepNew', { defaultMessage: '使用新的' })}
        </button>

        <button
          onClick={() => {
            if (showMergeEditor) {
              if (mergedContent.trim()) {
                handleResolve('merge', mergedContent.trim());
              }
            } else {
              setShowMergeEditor(true);
            }
          }}
          disabled={resolving || (showMergeEditor && !mergedContent.trim())}
          className={cn(
            'flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg',
            'text-xs font-medium transition-all duration-200',
            'border border-indigo-500/30 hover:border-indigo-500/50',
            'text-indigo-600 dark:text-indigo-400 hover:bg-indigo-500/5',
            showMergeEditor && mergedContent.trim() && 'bg-indigo-500/10',
          )}
        >
          {showMergeEditor ? <Pencil size={13} /> : <GitMerge size={13} />}
          {showMergeEditor
            ? t('conflict.confirmMerge', { defaultMessage: '确认合并' })
            : t('conflict.merge', { defaultMessage: '合并' })}
        </button>

        <button
          onClick={() => handleResolve('discard_both')}
          disabled={resolving}
          className={cn(
            'flex items-center justify-center gap-1 px-2.5 py-2 rounded-lg',
            'text-xs font-medium transition-all duration-200',
            'text-muted-foreground/60 hover:text-destructive',
            'hover:bg-destructive/5',
          )}
          title={t('conflict.discardBoth', { defaultMessage: '丢弃两者' })}
        >
          <Trash2 size={13} />
        </button>
      </div>
    </div>
  );
});

ConflictCard.displayName = 'ConflictCard';

export default ConflictCard;
