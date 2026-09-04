'use client';

/**
 * [INPUT]
 * @/lib/utils/classnameUtils::cn
 *
 * [OUTPUT]
 * GraphEmptyState: 3-State diagnostic empty and guided recovery states for Knowledge Graph.
 *
 * [POS]
 * 图谱三态精细化诊断引导组件。
 * 区分：1. 存储引擎未就绪 (storage_disabled)；2. 知识库冷启动零主张 (empty_knowledge)；3. 稀疏孤岛散点态 (sparse_islands)。
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { AlertCircle, Database, GitFork, RefreshCw, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export type GraphDiagnosisState = 'ready' | 'storage_disabled' | 'empty_knowledge' | 'sparse_islands';

interface GraphEmptyStateProps {
  state: GraphDiagnosisState;
  onRetry?: () => void;
  className?: string;
}

export const GraphEmptyState = memo<GraphEmptyStateProps>(({ state, onRetry, className }) => {
  const t = useTranslations('memory');

  if (state === 'storage_disabled') {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center rounded-lg border border-dashed border-destructive/40 bg-destructive/5 p-8 text-center',
          className,
        )}
      >
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-destructive/10 text-destructive mb-3">
          <Database className="h-5 w-5" />
        </div>
        <h4 className="text-sm font-semibold text-foreground">
          {t('commandCenter.graph.stateStorageDisabledTitle')}
        </h4>
        <p className="mt-1.5 max-w-sm text-xs text-muted-foreground">
          {t('commandCenter.graph.stateStorageDisabledDesc')}
        </p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            {t('commandCenter.graph.retry')}
          </button>
        )}
      </div>
    );
  }

  if (state === 'empty_knowledge') {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center rounded-lg border border-dashed border-border/70 bg-accent/10 p-8 text-center',
          className,
        )}
      >
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary mb-3">
          <Sparkles className="h-5 w-5" />
        </div>
        <h4 className="text-sm font-semibold text-foreground">
          {t('commandCenter.graph.stateEmptyKnowledgeTitle')}
        </h4>
        <p className="mt-1.5 max-w-sm text-xs text-muted-foreground">
          {t('commandCenter.graph.stateEmptyKnowledgeDesc')}
        </p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            {t('commandCenter.graph.refreshState')}
          </button>
        )}
      </div>
    );
  }

  if (state === 'sparse_islands') {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center rounded-lg border border-dashed border-amber-500/40 bg-amber-500/5 p-8 text-center',
          className,
        )}
      >
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 mb-3">
          <GitFork className="h-5 w-5" />
        </div>
        <h4 className="text-sm font-semibold text-foreground">
          {t('commandCenter.graph.stateSparseIslandsTitle')}
        </h4>
        <p className="mt-1.5 max-w-sm text-xs text-muted-foreground">
          {t('commandCenter.graph.stateSparseIslandsDesc')}
        </p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            {t('commandCenter.graph.recheckAssociations')}
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center rounded-lg border border-dashed border-border/70 p-8 text-center',
        className,
      )}
    >
      <AlertCircle className="h-6 w-6 text-muted-foreground/60 mb-2" />
      <p className="text-sm text-muted-foreground">{t('commandCenter.graph.empty')}</p>
    </div>
  );
});

GraphEmptyState.displayName = 'GraphEmptyState';
