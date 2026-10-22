/**
 * [INPUT]
 * - next-intl::useTranslations (POS: 国际化翻译)
 *
 * [OUTPUT]
 * - KanbanBoardHeader (default): 看板标题行（返回 / 名称 / 模板创建 / 批量规范化 / 重规划 / 泳道开关 / 刷新）
 *
 * [POS]
 * 看板主视图的标题与全局动作入口；只负责展示与触发回调，状态与副作用都在主视图。
 */
'use client';

import { useTranslations } from 'next-intl';
import { Layers, Sparkles, Users, GitCompare } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { KanbanBoard } from '@/services/kanban';

interface KanbanBoardHeaderProps {
  board: KanbanBoard;
  triageCount: number;
  specifyAllLoading: boolean;
  laneByProfile: boolean;
  onBack: () => void;
  onOpenPipelineWizard: () => void;
  onSpecifyAll: () => void;
  onOpenReplan: () => void;
  onToggleLaneByProfile: () => void;
  onRefresh: () => void;
}

export default function KanbanBoardHeader({
  board,
  triageCount,
  specifyAllLoading,
  laneByProfile,
  onBack,
  onOpenPipelineWizard,
  onSpecifyAll,
  onOpenReplan,
  onToggleLaneByProfile,
  onRefresh,
}: KanbanBoardHeaderProps) {
  const t = useTranslations('kanban');

  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="p-1.5 rounded-full hover:bg-muted transition-colors text-sm">
          &larr;
        </button>
        <div>
          <h2 className="text-base font-semibold">{board.name}</h2>
          {board.description && <p className="text-xs text-muted-foreground mt-0.5">{board.description}</p>}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={onOpenPipelineWizard}
          className="text-xs px-2.5 py-1 rounded-full bg-primary/10 text-primary hover:bg-primary/20 transition-colors inline-flex items-center gap-1"
          title={t('pipelineFromTemplateHint')}
        >
          <Layers className="w-3 h-3" />
          {t('pipelineFromTemplate')}
        </button>
        {triageCount > 0 && (
          <button
            onClick={onSpecifyAll}
            disabled={specifyAllLoading}
            className="text-xs px-2.5 py-1 rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 hover:bg-purple-500/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-1"
            title={t('specifyAllHint')}
          >
            {specifyAllLoading ? (
              <span className="w-1.5 h-1.5 rounded-full bg-purple-500 animate-pulse" />
            ) : (
              <Sparkles className="w-3 h-3" />
            )}
            {t('specifyAll', { count: triageCount })}
          </button>
        )}
        <button
          onClick={onOpenReplan}
          className="text-xs px-2.5 py-1 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 hover:bg-blue-500/20 transition-colors inline-flex items-center gap-1"
          title={t('replanTitle')}
        >
          <GitCompare className="w-3 h-3" />
          {t('replanTitle')}
        </button>
        <button
          onClick={onToggleLaneByProfile}
          className={cn(
            'text-xs px-2.5 py-1 rounded-full transition-colors inline-flex items-center gap-1',
            laneByProfile
              ? 'bg-chart-4/10 text-chart-4 hover:bg-chart-4/20'
              : 'hover:bg-muted text-muted-foreground hover:text-foreground',
          )}
          title={t('laneByProfileHint')}
        >
          <Users className="w-3 h-3" />
          {t('laneByProfile')}
        </button>
        <button
          onClick={onRefresh}
          className="text-xs px-2.5 py-1 rounded-full hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
          title={t('refresh')}
        >
          {t('refresh')}
        </button>
      </div>
    </div>
  );
}
