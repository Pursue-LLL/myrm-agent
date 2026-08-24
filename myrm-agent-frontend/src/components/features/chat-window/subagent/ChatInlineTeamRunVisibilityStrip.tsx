/**
 * [INPUT]
 * store/chat/useSubagentStore::useSubagentStore (POS: 子智能体状态管理 Zustand Store)
 * components/agent/AgentAvatar::AgentAvatar (POS: 智能体头像展示组件)
 * components/features/chat-window/subagent/SubagentStream::STATUS_ICON_MAP (POS: 子智能体状态图标映射表)
 * lib/utils::cn (POS: Tailwind CSS 类名合并工具函数)
 *
 * [OUTPUT]
 * ChatInlineTeamRunVisibilityStrip: 聊天输入区常驻轻量化子智能体团队运行可见性微条
 *
 * [POS]
 * 主对话窗口输入区上方的常驻子智能体运行状态微条。在不打扰主聊天体验的前提下，提供多子智能体并发状态堆叠、优先级抢占告警、微进度条与深链交互。
 */

'use client';

import React, { useMemo, useCallback, useState, useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { AlertCircle, CheckCircle2, ChevronRight, Hourglass, Users } from 'lucide-react';
import { useSubagentStore, type SubagentNode, type SubagentStatus } from '@/store/chat/useSubagentStore';
import { AgentAvatar } from '@/components/agent/AgentAvatar';
import { STATUS_ICON_MAP } from './SubagentStream';
import { cn } from '@/lib/utils';

export interface ChatInlineTeamRunVisibilityStripProps {
  className?: string;
  onOpenDashboard?: (taskId?: string) => void;
}

const ACTIVE_STATUS_SET: ReadonlySet<SubagentStatus> = new Set<SubagentStatus>([
  'pending',
  'running',
  'verifying',
  'pending_approval',
  'interrupted',
  'checkpoint',
]);

export function ChatInlineTeamRunVisibilityStrip({
  className,
  onOpenDashboard,
}: ChatInlineTeamRunVisibilityStripProps) {
  const t = useTranslations('subagentDashboard');
  const nodes = useSubagentStore((s) => s.nodes);

  const nodeList = useMemo(() => Object.values(nodes).filter((n) => !n.internal), [nodes]);

  const activeNodes = useMemo(
    () => nodeList.filter((n) => ACTIVE_STATUS_SET.has(n.status) || Boolean(n.stale)),
    [nodeList],
  );

  const totalCount = nodeList.length;
  const activeCount = activeNodes.length;

  // ── Graceful completion exit buffer ─────────────────────────────────
  const [showCompletedBuffer, setShowCompletedBuffer] = useState(false);
  const [prevCompletedTotal, setPrevCompletedTotal] = useState(0);
  const prevActiveCountRef = useRef(activeCount);

  useEffect(() => {
    const prevActive = prevActiveCountRef.current;
    if (prevActive > 0 && activeCount === 0 && totalCount > 0) {
      const allDone = nodeList.every(
        (n) =>
          n.status === 'completed' || n.status === 'failed' || n.status === 'timed_out' || n.status === 'cancelled',
      );
      if (allDone) {
        setPrevCompletedTotal(totalCount);
        setShowCompletedBuffer(true);
        const timer = window.setTimeout(() => {
          setShowCompletedBuffer(false);
        }, 2500);
        return () => window.clearTimeout(timer);
      }
    }
    prevActiveCountRef.current = activeCount;
  }, [activeCount, totalCount, nodeList]);

  const handleOpen = useCallback(
    (taskId?: string) => {
      if (onOpenDashboard) {
        onOpenDashboard(taskId);
      } else {
        window.dispatchEvent(
          new CustomEvent('open_subagent_dashboard', {
            detail: taskId ? { taskId } : undefined,
          }),
        );
      }
    },
    [onOpenDashboard],
  );

  // ── Priority preemption: pending_approval > stale > failed > running/verifying > pending ────
  const { priorityNode, alertLevel, activeStepText } = useMemo(() => {
    if (activeCount === 0) {
      return { priorityNode: null, alertLevel: 'normal', activeStepText: '' };
    }

    const pendingApprovalNode = activeNodes.find((n) => n.status === 'pending_approval');
    if (pendingApprovalNode) {
      const pendingCount = activeNodes.filter((n) => n.status === 'pending_approval').length;
      return {
        priorityNode: pendingApprovalNode,
        alertLevel: 'approval' as const,
        activeStepText: t('inlineStripPendingApprovalAlert', { count: pendingCount }),
      };
    }

    const staleNode = activeNodes.find((n) => n.stale);
    if (staleNode) {
      const staleCount = activeNodes.filter((n) => n.stale).length;
      return {
        priorityNode: staleNode,
        alertLevel: 'stale' as const,
        activeStepText: t('inlineStripStaleAlert', { count: staleCount }),
      };
    }

    const runningOrVerifying = activeNodes.filter((n) => n.status === 'running' || n.status === 'verifying');
    if (runningOrVerifying.length > 0) {
      const primary = runningOrVerifying[runningOrVerifying.length - 1];
      const step = primary.last_tool || primary.description || primary.agent_type || t('inlineStripRunning');
      return {
        priorityNode: primary,
        alertLevel: 'normal' as const,
        activeStepText: step,
      };
    }

    const pendingNode = activeNodes.find((n) => n.status === 'pending');
    if (pendingNode) {
      return {
        priorityNode: pendingNode,
        alertLevel: 'pending' as const,
        activeStepText: pendingNode.description || t('inlineStripPending'),
      };
    }

    const fallbackNode = activeNodes[activeNodes.length - 1];
    return {
      priorityNode: fallbackNode,
      alertLevel: 'normal' as const,
      activeStepText: fallbackNode?.description || t('inlineStripRunning'),
    };
  }, [activeNodes, activeCount, t]);

  // ── Weighted average progress ────────────────────────────────────────
  const averageProgress = useMemo(() => {
    if (activeCount === 0) {
      return 100;
    }
    const sum = activeNodes.reduce((acc, curr) => acc + (typeof curr.progress === 'number' ? curr.progress : 0), 0);
    return Math.min(100, Math.max(0, Math.round(sum / activeCount)));
  }, [activeNodes, activeCount]);

  if (activeCount === 0 && !showCompletedBuffer) {
    return null;
  }

  // ── Render completed graceful buffer state ───────────────────────────
  if (activeCount === 0 && showCompletedBuffer) {
    return (
      <div
        data-testid="chat-inline-team-run-visibility-strip"
        onClick={() => handleOpen()}
        className={cn(
          'group relative overflow-hidden flex items-center justify-between gap-3 px-3 py-2 mb-2 rounded-xl border border-green-500/30 bg-green-500/10 hover:bg-green-500/15 backdrop-blur-md cursor-pointer transition-all duration-300 shadow-sm animate-in fade-in',
          className,
        )}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handleOpen();
          }
        }}
        title={t('inlineStripOpenTooltip')}
      >
        <div className="flex items-center gap-2 text-xs text-green-700 dark:text-green-300 font-medium">
          <CheckCircle2 className="w-4 h-4 text-green-600 dark:text-green-400 shrink-0" />
          <span>{t('inlineStripCompleted', { count: prevCompletedTotal })}</span>
        </div>
        <div className="flex items-center gap-1 text-xs text-muted-foreground group-hover:text-primary transition-colors shrink-0">
          <span className="hidden sm:inline font-medium">{t('inlineStripViewLive')}</span>
          <ChevronRight className="w-3.5 h-3.5" />
        </div>
      </div>
    );
  }

  const visibleAvatars = activeNodes.slice(0, 3);
  const remainingCount = activeCount - visibleAvatars.length;

  return (
    <div
      data-testid="chat-inline-team-run-visibility-strip"
      onClick={() => handleOpen(priorityNode?.task_id)}
      className={cn(
        'group relative overflow-hidden flex items-center justify-between gap-3 px-3 py-2 mb-2 rounded-xl border backdrop-blur-md cursor-pointer transition-all duration-200 shadow-sm hover:shadow',
        alertLevel === 'approval'
          ? 'border-amber-500/60 bg-amber-500/10 hover:bg-amber-500/15 ring-1 ring-amber-500/30'
          : alertLevel === 'stale'
            ? 'border-yellow-500/60 bg-yellow-500/10 hover:bg-yellow-500/15'
            : 'border-border/80 bg-background/80 hover:bg-accent/40',
        className,
      )}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handleOpen(priorityNode?.task_id);
        }
      }}
      title={t('inlineStripOpenTooltip')}
    >
      <div className="flex items-center gap-2.5 min-w-0 flex-1">
        {/* Avatar Stack */}
        <div className="flex items-center -space-x-2 shrink-0">
          {visibleAvatars.map((node) => {
            const statusConfig = STATUS_ICON_MAP[node.status] ?? STATUS_ICON_MAP.running;
            return (
              <div
                key={node.task_id}
                data-testid={`inline-avatar-${node.task_id}`}
                onClick={(e) => {
                  e.stopPropagation();
                  handleOpen(node.task_id);
                }}
                className="relative inline-flex items-center justify-center ring-2 ring-background rounded-full hover:scale-110 transition-transform"
                title={`${node.agent_type || node.role || 'Agent'} (${t(`statusLabel.${node.status}`)})`}
              >
                <AgentAvatar
                  name={node.agent_type || node.role || 'Agent'}
                  agentId={node.agent_type}
                  size="sm"
                  className="w-6 h-6 text-[10px]"
                />
                <span
                  className={cn(
                    'absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full ring-1 ring-background',
                    statusConfig.className.replace('text-', 'bg-'),
                    statusConfig.spin ? 'animate-pulse' : '',
                  )}
                />
              </div>
            );
          })}
          {remainingCount > 0 && (
            <div className="flex items-center justify-center w-6 h-6 rounded-full bg-muted text-[10px] font-semibold text-muted-foreground ring-2 ring-background">
              +{remainingCount}
            </div>
          )}
        </div>

        {/* Text Details */}
        <div className="flex items-center gap-2 min-w-0 flex-1 text-xs">
          <span
            className={cn(
              'font-medium shrink-0 flex items-center gap-1',
              alertLevel === 'approval'
                ? 'text-amber-600 dark:text-amber-400 font-semibold'
                : alertLevel === 'stale'
                  ? 'text-yellow-600 dark:text-yellow-400 font-semibold'
                  : 'text-foreground',
            )}
          >
            {alertLevel === 'approval' ? (
              <Hourglass className="w-3.5 h-3.5 text-amber-500 animate-spin" />
            ) : alertLevel === 'stale' ? (
              <AlertCircle className="w-3.5 h-3.5 text-yellow-500" />
            ) : (
              <Users className="w-3.5 h-3.5 text-primary" />
            )}
            {t('inlineStripActiveSummary', { count: activeCount })}
          </span>
          <span className="text-muted-foreground/60 shrink-0">·</span>
          <span
            className={cn(
              'truncate',
              alertLevel === 'approval'
                ? 'text-amber-700 dark:text-amber-300 font-medium'
                : alertLevel === 'stale'
                  ? 'text-yellow-700 dark:text-yellow-300 font-medium'
                  : 'text-muted-foreground',
            )}
            title={activeStepText}
          >
            {activeStepText}
          </span>
        </div>
      </div>

      {/* Right Action Hint */}
      <div className="flex items-center gap-1 text-xs text-muted-foreground group-hover:text-primary transition-colors shrink-0">
        <span className="hidden sm:inline font-medium">{t('inlineStripViewLive')}</span>
        <ChevronRight className="w-3.5 h-3.5" />
      </div>

      {/* 2px Thin Progress Track */}
      {averageProgress > 0 && averageProgress < 100 && (
        <div
          data-testid="inline-progress-track"
          className="absolute bottom-0 left-0 right-0 h-[2px] bg-muted/40 overflow-hidden"
        >
          <div
            className={cn(
              'h-full transition-all duration-300 ease-out',
              alertLevel === 'approval' ? 'bg-amber-500' : alertLevel === 'stale' ? 'bg-yellow-500' : 'bg-primary',
            )}
            style={{ width: `${averageProgress}%` }}
          />
        </div>
      )}
    </div>
  );
}

export default ChatInlineTeamRunVisibilityStrip;
