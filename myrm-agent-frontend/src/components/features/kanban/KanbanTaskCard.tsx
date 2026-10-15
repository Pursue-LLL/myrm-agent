/**
 * [INPUT]
 * - @/services/kanban (POS: 任务类型与完成意图判定)
 * - @/lib/kanban/kanbanDecisionFrame::deriveTaskDecisionFrame (POS: 责任方与推荐动作推导)
 * - ./kanban-styles (POS: 优先级、状态点、诊断严重度样式与耗时格式化)
 * - ./useKanbanTaskCardDetails、./KanbanTaskCardDetails (POS: 展开详情的数据层与面板)
 * - ./KanbanTaskCardActions、./KanbanSpecifyDialog、./KanbanDecomposeDialog (POS: 卡片菜单与两个任务对话框)
 * - @/hooks/agent/useAgentName (POS: Agent 显示名)
 *
 * [OUTPUT]
 * - KanbanTaskCard (default): 看板列里的任务卡片：优先级、Agent、责任方与推荐动作，点击展开运行记录、事件、依赖与评论
 *
 * [POS]
 * 任务在看板上的展示与快捷操作单元；展开详情在首次展开时才加载（`useKanbanTaskCardDetails`），
 * 完整编辑通过 onOpenTaskDrawer 交给任务抽屉。
 */
'use client';

import { useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import {
  Clock,
  ExternalLink,
  GitBranch,
  Paperclip,
  User,
  ShieldAlert,
  ShieldCheck,
  UserCheck,
  Bot,
} from 'lucide-react';
import { deriveTaskDecisionFrame } from '@/lib/kanban/kanbanDecisionFrame';
import { PRIORITY_INDICATORS, DIAGNOSTIC_SEVERITY_STYLES, formatDuration } from './kanban-styles';
import KanbanTaskCardActions from './KanbanTaskCardActions';
import KanbanTaskCardDetails from './KanbanTaskCardDetails';
import KanbanSpecifyDialog from './KanbanSpecifyDialog';
import KanbanDecomposeDialog from './KanbanDecomposeDialog';
import { useKanbanTaskCardDetails } from './useKanbanTaskCardDetails';
import { useAgentName } from '@/hooks/agent/useAgentName';

function ScheduledCountdown({ until }: { until: string }) {
  const [remaining, setRemaining] = useState('');
  useEffect(() => {
    const update = () => {
      const diff = new Date(until).getTime() - Date.now();
      if (diff <= 0) {
        setRemaining('auto-unblocking...');
        return;
      }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setRemaining(h > 0 ? `${h}h ${m}m` : m > 0 ? `${m}m ${s}s` : `${s}s`);
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [until]);
  return (
    <span className="inline-flex items-center gap-0.5 text-[10px] text-chart-4 font-mono">
      <Clock className="w-3 h-3" /> {remaining}
    </span>
  );
}

interface KanbanTaskCardProps {
  task: KanbanTask;
  allTasks: KanbanTask[];
  onMove: (taskId: string, status: TaskStatus) => void;
  onDelete: (taskId: string) => void;
  onRefresh: () => void;
  onReclaim?: (taskId: string) => void;
  onOpenTaskDrawer?: (taskId: string) => void;
  queuedByConcurrency?: boolean;
}

export default function KanbanTaskCard({
  task,
  allTasks,
  onMove,
  onDelete,
  onRefresh,
  onReclaim,
  onOpenTaskDrawer,
  queuedByConcurrency = false,
}: KanbanTaskCardProps) {
  const t = useTranslations('kanban');
  const agentName = useAgentName(task.agent_id);
  const decisionFrame = useMemo(() => deriveTaskDecisionFrame(task), [task]);
  const [specifyOpen, setSpecifyOpen] = useState(false);
  const [decomposeOpen, setDecomposeOpen] = useState(false);
  const details = useKanbanTaskCardDetails({ task, allTasks, onRefresh });

  const loadedChildren = details.children;
  const progressPill = useMemo(() => {
    if (loadedChildren.length > 0) {
      const done = loadedChildren.filter((c) => c.status === 'completed' || c.status === 'archived').length;
      return { done, total: loadedChildren.length };
    }
    if (task.children_total > 0) {
      return { done: task.children_done, total: task.children_total };
    }
    return null;
  }, [loadedChildren, task.children_total, task.children_done]);

  const relativeTime = useMemo(() => {
    const diff = Date.now() - new Date(task.created_at).getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) {
      return t('justNow');
    }
    if (minutes < 60) {
      return t('minutesAgo', { count: minutes });
    }
    const hours = Math.floor(minutes / 60);
    if (hours < 24) {
      return t('hoursAgo', { count: hours });
    }
    const days = Math.floor(hours / 24);
    return t('daysAgo', { count: days });
  }, [task.created_at, t]);

  const diagSummary = task.diagnostics_summary;

  return (
    <div
      id={`kanban-task-${task.task_id}`}
      data-theme-shell="surface"
      className="relative group rounded-full border bg-background hover:shadow transition-shadow"
    >
      <div className="p-2.5">
        <div className={cn('absolute left-0 top-2 bottom-2 w-0.5 rounded-full', PRIORITY_INDICATORS[task.priority])} />

        <div className="pl-2">
          <div className="flex items-start justify-between gap-1">
            <p className="text-sm font-medium leading-tight line-clamp-2 flex-1">{task.title}</p>
            <KanbanTaskCardActions
              task={task}
              onMove={onMove}
              onDelete={onDelete}
              onReclaim={onReclaim}
              onOpenTaskDrawer={onOpenTaskDrawer}
              onSpecify={() => setSpecifyOpen(true)}
              onDecompose={() => setDecomposeOpen(true)}
            />
            <button
              onClick={details.toggleExpand}
              className="p-0.5 rounded hover:bg-muted shrink-0 text-muted-foreground text-xs"
              aria-label={t('taskDetails')}
              aria-expanded={details.expanded}
            >
              {details.expanded ? '\u25B2' : '\u25BC'}
            </button>
          </div>
          {task.description && <p className="text-xs text-muted-foreground mt-1 line-clamp-1">{task.description}</p>}

          {/* Decision Frame Micro-strip */}
          <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
            {decisionFrame.waitingEntity === 'human' && (
              <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 font-medium">
                <UserCheck className="w-3 h-3" />
                {t('decisionWaitingHuman')}
              </span>
            )}
            {decisionFrame.waitingEntity === 'agent' && (
              <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md bg-chart-4/10 text-chart-4 border border-chart-4/20 font-medium">
                <Bot className="w-3 h-3" />
                {t('decisionWaitingAgent')}
              </span>
            )}
            {decisionFrame.safetyTier === 'hitl_guarded' && (
              <span
                className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md bg-destructive/10 text-destructive border border-destructive/20 font-medium"
                title={t('decisionHitlGuarded')}
              >
                <ShieldAlert className="w-3 h-3" />
                {t('decisionHitlGuarded')}
              </span>
            )}
            {decisionFrame.safetyTier === 'safe_auto' && decisionFrame.waitingEntity === 'agent' && (
              <span
                className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md bg-chart-2/10 text-chart-2 border border-chart-2/20 font-medium"
                title={t('decisionSafeAuto')}
              >
                <ShieldCheck className="w-3 h-3" />
                {t('decisionSafeAuto')}
              </span>
            )}
          </div>

          {/* Recommended Action / Note */}
          <p
            className={cn(
              'text-[10px] mt-1 truncate font-medium',
              decisionFrame.hasAttention ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground',
            )}
            title={t(decisionFrame.recommendedActionKey, {
              defaultValue: decisionFrame.recommendedActionFallback,
            })}
          >
            {t(decisionFrame.recommendedActionKey, {
              defaultValue: decisionFrame.recommendedActionFallback,
            })}
          </p>

          <div className="flex items-center gap-1.5 mt-1 flex-wrap">
            {task.branch && (
              <span
                className="inline-flex items-center text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/10 text-blue-500 border border-blue-500/20 truncate max-w-[100px]"
                title={task.branch}
              >
                <GitBranch className="w-3 h-3 mr-1 shrink-0" />
                <span className="truncate">{task.branch}</span>
              </span>
            )}
            {task.agent_id && agentName && (
              <span
                className="text-[10px] px-1.5 py-0.5 rounded-full bg-chart-4/10 text-chart-4 border border-chart-4/20 truncate max-w-[100px]"
                title={agentName}
              >
                {agentName}
              </span>
            )}
            {task.dep_count > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                {t('depBadge', { count: task.dep_count })}
              </span>
            )}
            {progressPill && (
              <span
                className={cn(
                  'text-[10px] px-1.5 py-0.5 rounded-full border',
                  progressPill.done === progressPill.total
                    ? 'bg-chart-2/10 text-chart-2 border-chart-2/20'
                    : 'bg-primary/10 text-primary border-primary/20',
                )}
              >
                {progressPill.done}/{progressPill.total}
              </span>
            )}
            {task.comment_count > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                {t('commentBadge', { count: task.comment_count })}
              </span>
            )}
            {task.attachments && task.attachments.length > 0 && (
              <button
                type="button"
                data-testid={`kanban-task-attachment-badge-${task.task_id}`}
                onPointerDown={(e) => {
                  e.stopPropagation();
                }}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onOpenTaskDrawer?.(task.task_id);
                }}
                className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 transition-colors cursor-pointer touch-manipulation"
                title={t('viewAttachmentsHint')}
                aria-label={t('viewAttachmentsHint')}
              >
                <Paperclip className="w-2.5 h-2.5" />
                {task.attachments.length}
              </button>
            )}
            {task.extra_skill_ids && task.extra_skill_ids.length > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-chart-3/10 text-chart-3 border border-chart-3/20 truncate max-w-[120px]">
                {task.extra_skill_ids.join(', ')}
              </span>
            )}
            {task.max_runtime_seconds != null && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-chart-5/10 text-chart-5 border border-chart-5/20">
                {t('timeoutLabel')}: {formatDuration(task.max_runtime_seconds)}
              </span>
            )}
            {task.goal_mode && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-chart-4/10 text-chart-4 border border-chart-4/20">
                {t('goalModeBadge')}
                {task.goal_max_turns ? ` ×${task.goal_max_turns}` : ''}
              </span>
            )}
            {task.retry_count > 0 && (
              <span className="text-[10px] text-muted-foreground">
                {t('retries')}: {task.retry_count}/{task.max_retries}
              </span>
            )}
            {task.blocked_reason && (
              <span className="inline-flex items-center gap-0.5 text-[10px] text-destructive line-clamp-1">
                {task.block_kind === 'scheduled' && <Clock className="w-3 h-3 shrink-0" />}
                {task.block_kind === 'external' && <ExternalLink className="w-3 h-3 shrink-0" />}
                {task.block_kind === 'human' && <User className="w-3 h-3 shrink-0" />}
                {task.blocked_reason}
              </span>
            )}
            {task.block_kind === 'scheduled' && task.scheduled_until && (
              <ScheduledCountdown until={task.scheduled_until} />
            )}
            {task.status === 'backlog' && (
              <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-chart-5/10 text-chart-5 border border-chart-5/20">
                <span className="w-1 h-1 rounded-full bg-chart-5 animate-pulse" />
                {t('waitingForDeps')}
              </span>
            )}
            {task.status === 'ready' && queuedByConcurrency && (
              <span
                data-testid="kanban-task-queued-badge"
                className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20"
              >
                <span className="w-1 h-1 rounded-full bg-amber-500 animate-pulse" />
                {t('queuedForConcurrency')}
              </span>
            )}
            {task.status === 'triage' && (
              <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                <span className="w-1 h-1 rounded-full bg-purple-500 animate-pulse" />
                {t('triagePending')}
              </span>
            )}
            {diagSummary && diagSummary.count > 0 && diagSummary.max_severity && (
              <span
                className={cn(
                  'inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full border',
                  DIAGNOSTIC_SEVERITY_STYLES[diagSummary.max_severity]?.badge ?? 'bg-muted text-muted-foreground',
                )}
              >
                {t('diagnosticBadge', { count: diagSummary.count })}
              </span>
            )}
            <span className="text-[9px] text-muted-foreground/60 ml-auto shrink-0">{relativeTime}</span>
          </div>
          {task.attachments && task.attachments.length > 0 && (
            <p className="text-[9px] text-muted-foreground/70 mt-0.5">{t('openDetailsHint')}</p>
          )}
        </div>
      </div>

      <KanbanSpecifyDialog
        task={specifyOpen ? task : null}
        open={specifyOpen}
        onOpenChange={setSpecifyOpen}
        onApplied={onRefresh}
      />
      <KanbanDecomposeDialog
        task={decomposeOpen ? task : null}
        open={decomposeOpen}
        onOpenChange={setDecomposeOpen}
        onApplied={onRefresh}
      />

      {details.expanded && <KanbanTaskCardDetails details={details} progressPill={progressPill} />}
    </div>
  );
}
