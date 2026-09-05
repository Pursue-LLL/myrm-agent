'use client';

/**
 * [INPUT]
 * @/services/memory/commandCenter::MemoryCommandGraphResponse['graph_state']
 *
 * [OUTPUT]
 * GraphDiagnosticEmptyState: 3-State precision diagnostic and actionable empty state card for Knowledge Graph.
 *
 * [POS]
 * 图谱三态排障空态组件。精确区分：存储离线、冷启动零主张、孤立散点态，提供针对性排障指引。
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Database, Network, Sparkles, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

interface GraphDiagnosticEmptyStateProps {
  state: 'storage_disabled' | 'empty_knowledge' | 'sparse_islands' | 'unknown';
  onRetry?: () => void;
  className?: string;
}

export const GraphDiagnosticEmptyState = memo<GraphDiagnosticEmptyStateProps>(({
  state,
  onRetry,
  className,
}) => {
  const t = useTranslations('memory');

  const configs = {
    storage_disabled: {
      icon: Database,
      title: t('commandCenter.graph.stateStorageDisabledTitle'),
      desc: t('commandCenter.graph.stateStorageDisabledDesc'),
      actionLabel: t('commandCenter.graph.refreshState'),
      color: 'text-amber-500',
    },
    empty_knowledge: {
      icon: Sparkles,
      title: t('commandCenter.graph.stateEmptyKnowledgeTitle'),
      desc: t('commandCenter.graph.stateEmptyKnowledgeDesc'),
      actionLabel: t('commandCenter.graph.refreshState'),
      color: 'text-primary',
    },
    sparse_islands: {
      icon: Network,
      title: t('commandCenter.graph.stateSparseIslandsTitle'),
      desc: t('commandCenter.graph.stateSparseIslandsDesc'),
      actionLabel: t('commandCenter.graph.recheckAssociations'),
      color: 'text-blue-500',
    },
    unknown: {
      icon: Network,
      title: t('commandCenter.graph.unavailable'),
      desc: t('commandCenter.graph.empty'),
      actionLabel: t('commandCenter.graph.retry'),
      color: 'text-muted-foreground',
    },
  };

  const current = configs[state] ?? configs.unknown;
  const IconComponent = current.icon;

  return (
    <div
      role="status"
      className={cn(
        'flex flex-col items-center justify-center rounded-lg border border-dashed border-border/70 p-8 text-center bg-accent/5 backdrop-blur-xs',
        className,
      )}
    >
      <div className={cn('mb-3 inline-flex h-10 w-10 items-center justify-center rounded-full bg-accent/40', current.color)}>
        <IconComponent className="h-5 w-5" />
      </div>
      <h3 className="text-sm font-semibold text-foreground">{current.title}</h3>
      <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">{current.desc}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-border/80 bg-background px-3 py-1.5 text-xs font-medium text-foreground shadow-xs hover:bg-accent/40 transition-colors"
        >
          <RefreshCw className="h-3.5 w-3.5 text-muted-foreground" />
          {current.actionLabel}
        </button>
      )}
    </div>
  );
});

GraphDiagnosticEmptyState.displayName = 'GraphDiagnosticEmptyState';
