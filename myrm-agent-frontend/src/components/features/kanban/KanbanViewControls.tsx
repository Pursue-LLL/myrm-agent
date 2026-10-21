/**
 * [INPUT]
 * - @/components/primitives/tabs (POS: 标签页基础组件)
 * - @/lib/kanban/kanbanDecisionFrame::ResponsibilityFilter (POS: 看板责任人筛选类型)
 *
 * [OUTPUT]
 * - KanbanViewMode: 看板视图类型（board / graph / activity）
 * - KanbanViewControls (default): 视图切换标签 + 看板视图下的责任人筛选
 *
 * [POS]
 * 看板主视图的视图与筛选控件；受控组件，状态与持久化都在主视图。
 */
'use client';

import { useTranslations } from 'next-intl';
import { UserCheck, Bot } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { ResponsibilityFilter } from '@/lib/kanban/kanbanDecisionFrame';
import { Tabs, TabsList, TabsTrigger } from '@/components/primitives/tabs';

export type KanbanViewMode = 'board' | 'graph' | 'activity';

interface KanbanViewControlsProps {
  viewMode: KanbanViewMode;
  responsibilityFilter: ResponsibilityFilter;
  onViewModeChange: (mode: KanbanViewMode) => void;
  onResponsibilityFilterChange: (filter: ResponsibilityFilter) => void;
}

export default function KanbanViewControls({
  viewMode,
  responsibilityFilter,
  onViewModeChange,
  onResponsibilityFilterChange,
}: KanbanViewControlsProps) {
  const t = useTranslations('kanban');

  return (
    <div className="flex items-center justify-between gap-2 flex-wrap">
      <Tabs value={viewMode} onValueChange={(v) => onViewModeChange(v as KanbanViewMode)}>
        <TabsList className="h-8">
          <TabsTrigger value="board" className="text-xs px-3 py-1">
            {t('viewBoard')}
          </TabsTrigger>
          <TabsTrigger value="graph" className="text-xs px-3 py-1" data-testid="kanban-view-graph">
            {t('viewGraph')}
          </TabsTrigger>
          <TabsTrigger value="activity" className="text-xs px-3 py-1">
            {t('viewActivity')}
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {viewMode === 'board' && (
        <div className="flex items-center gap-1 bg-muted/40 p-0.5 rounded-lg border border-border/40">
          <button
            type="button"
            onClick={() => onResponsibilityFilterChange('all')}
            className={cn(
              'text-xs px-2.5 py-1 rounded-md transition-colors font-medium',
              responsibilityFilter === 'all'
                ? 'bg-background text-foreground shadow-xs'
                : 'text-muted-foreground hover:text-foreground',
            )}
            title={t('decisionFilterAllHint')}
          >
            {t('decisionFilterAll')}
          </button>
          <button
            type="button"
            onClick={() => onResponsibilityFilterChange('needs_action')}
            className={cn(
              'text-xs px-2.5 py-1 rounded-md transition-colors inline-flex items-center gap-1 font-medium',
              responsibilityFilter === 'needs_action'
                ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 shadow-xs'
                : 'text-muted-foreground hover:text-amber-600 dark:hover:text-amber-400',
            )}
            title={t('decisionFilterNeedsActionHint')}
          >
            <UserCheck className="w-3.5 h-3.5" />
            {t('decisionFilterNeedsAction')}
          </button>
          <button
            type="button"
            onClick={() => onResponsibilityFilterChange('autonomous')}
            className={cn(
              'text-xs px-2.5 py-1 rounded-md transition-colors inline-flex items-center gap-1 font-medium',
              responsibilityFilter === 'autonomous'
                ? 'bg-chart-4/10 text-chart-4 border border-chart-4/20 shadow-xs'
                : 'text-muted-foreground hover:text-chart-4',
            )}
            title={t('decisionFilterAutonomousHint')}
          >
            <Bot className="w-3.5 h-3.5" />
            {t('decisionFilterAutonomous')}
          </button>
        </div>
      )}
    </div>
  );
}
