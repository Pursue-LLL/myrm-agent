'use client';

/**
 * 跨端统一「需要你」中断队列抽屉组件
 *
 * 聚合审批、目标评审、看板阻塞、承诺履约、任务重试、预算阈值与无人值守待答卡，
 * 呈现清晰的「为什么停」与「在等什么」，提供一键深链与防静默遗漏的理由化忽略机制。
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  ShieldAlert,
  CheckCircle,
  Clock,
  ExternalLink,
  X,
  CheckSquare,
  Square,
  AlertTriangle,
  RotateCcw,
  HelpCircle,
  DollarSign,
  UserCheck,
} from 'lucide-react';
import type { InterruptionSource, NeedsYouItem } from './needsYouTypes';
import { useNeedsYouQueueStore } from './useNeedsYouQueueStore';
import { sortNeedsYouQueue } from './needsYouQueueEngine';

export interface NeedsYouQueueDrawerProps {
  onNavigateToDeepLink?: (url: string, item: NeedsYouItem) => void;
  className?: string;
}

function getSourceIcon(source: InterruptionSource) {
  switch (source) {
    case 'approval_pending':
      return <ShieldAlert className="w-3.5 h-3.5 text-amber-500" />;
    case 'goal_needs_review':
      return <UserCheck className="w-3.5 h-3.5 text-primary" />;
    case 'kanban_human_block':
      return <AlertTriangle className="w-3.5 h-3.5 text-orange-500" />;
    case 'commitment_due':
      return <Clock className="w-3.5 h-3.5 text-blue-500" />;
    case 'task_failed_retry':
      return <RotateCcw className="w-3.5 h-3.5 text-destructive" />;
    case 'budget_threshold':
      return <DollarSign className="w-3.5 h-3.5 text-amber-600" />;
    case 'unattended_clarification':
      return <HelpCircle className="w-3.5 h-3.5 text-purple-500" />;
    default:
      return <ShieldAlert className="w-3.5 h-3.5 text-muted-foreground" />;
  }
}

function getSourceBadgeLabel(source: InterruptionSource): string {
  switch (source) {
    case 'approval_pending':
      return '安全审批';
    case 'goal_needs_review':
      return '目标评审';
    case 'kanban_human_block':
      return '看板阻塞';
    case 'commitment_due':
      return '承诺到期';
    case 'task_failed_retry':
      return '失败重试';
    case 'budget_threshold':
      return '预算告警';
    case 'unattended_clarification':
      return '待答问题';
    default:
      return '待处理';
  }
}

export const NeedsYouQueueDrawer: React.FC<NeedsYouQueueDrawerProps> = ({
  onNavigateToDeepLink,
  className = '',
}) => {
  const isDrawerOpen = useNeedsYouQueueStore((s) => s.isDrawerOpen);
  const items = useNeedsYouQueueStore((s) => s.items);
  const focusedItemId = useNeedsYouQueueStore((s) => s.focusedItemId);
  const selectedItemIds = useNeedsYouQueueStore((s) => s.selectedItemIds);
  const isReasonModalOpen = useNeedsYouQueueStore((s) => s.isReasonModalOpen);
  const dismissTargetId = useNeedsYouQueueStore((s) => s.dismissTargetId);

  const closeDrawer = useNeedsYouQueueStore((s) => s.closeDrawer);
  const resolveInterruption = useNeedsYouQueueStore((s) => s.resolveInterruption);
  const dismissInterruption = useNeedsYouQueueStore((s) => s.dismissInterruption);
  const batchResolve = useNeedsYouQueueStore((s) => s.batchResolve);
  const openReasonModal = useNeedsYouQueueStore((s) => s.openReasonModal);
  const closeReasonModal = useNeedsYouQueueStore((s) => s.closeReasonModal);
  const toggleSelectItem = useNeedsYouQueueStore((s) => s.toggleSelectItem);
  const selectAll = useNeedsYouQueueStore((s) => s.selectAll);
  const deselectAll = useNeedsYouQueueStore((s) => s.deselectAll);

  const [dismissReasonInput, setDismissReasonInput] = useState('');
  const [reasonError, setReasonError] = useState('');
  const itemRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const sortedItems = sortNeedsYouQueue(items);
  const allSelected = sortedItems.length > 0 && selectedItemIds.length === sortedItems.length;

  // 自动滚动到被锚定聚焦的项
  useEffect(() => {
    if (focusedItemId && itemRefs.current[focusedItemId]) {
      const el = itemRefs.current[focusedItemId];
      if (el && typeof el.scrollIntoView === 'function') {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [focusedItemId, isDrawerOpen]);

  if (!isDrawerOpen) {
    return null;
  }

  const handleConfirmDismiss = () => {
    if (!dismissReasonInput.trim()) {
      setReasonError('请填写忽略理由，防静默遗漏');
      return;
    }
    if (dismissTargetId) {
      dismissInterruption(dismissTargetId, dismissReasonInput.trim());
      setDismissReasonInput('');
      setReasonError('');
    }
  };

  return (
    <aside
      aria-label="需要你中断队列抽屉"
      className={`fixed inset-y-0 right-0 z-[9990] w-full sm:w-[480px] bg-background border-l border-border shadow-2xl flex flex-col transition-all duration-300 animate-in slide-in-from-right ${className}`}
      data-testid="needs-you-queue-drawer"
    >
      {/* 头部标题与批量控制 */}
      <div className="p-4 border-b border-border flex items-center justify-between gap-3 bg-muted/20">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-amber-500/15 text-amber-600 flex items-center justify-center shrink-0">
            <ShieldAlert className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-foreground">需要你决策的中断队列</h2>
            <p className="text-[11px] text-muted-foreground">
              当前共 {sortedItems.length} 项在等候接手 · 已选 {selectedItemIds.length} 项
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={closeDrawer}
          className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          aria-label="关闭抽屉"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* 批量操作工具栏 */}
      {sortedItems.length > 0 && (
        <div className="px-4 py-2 border-b border-border/50 bg-secondary/30 flex items-center justify-between text-xs">
          <button
            type="button"
            onClick={allSelected ? deselectAll : selectAll}
            className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors"
          >
            {allSelected ? <CheckSquare className="w-3.5 h-3.5 text-primary" /> : <Square className="w-3.5 h-3.5" />}
            <span>全选</span>
          </button>

          {selectedItemIds.length > 0 && (
            <button
              type="button"
              onClick={() => batchResolve(selectedItemIds)}
              className="px-2.5 py-1 rounded bg-primary text-primary-foreground text-[11px] font-medium flex items-center gap-1 shadow-sm hover:bg-primary/90 transition-colors"
              data-testid="batch-approve-btn"
            >
              <CheckCircle className="w-3 h-3" />
              <span>批量通过 ({selectedItemIds.length})</span>
            </button>
          )}
        </div>
      )}

      {/* 待办卡片列表 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {sortedItems.length === 0 ? (
          <div className="py-16 text-center text-xs text-muted-foreground">
            <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center mx-auto mb-2 text-muted-foreground">
              <CheckCircle className="w-5 h-5 text-emerald-500" />
            </div>
            所有阻塞性任务均已顺利接手，系统正在全自主高效运转
          </div>
        ) : (
          sortedItems.map((item) => {
            const isSelected = selectedItemIds.includes(item.id);
            const isFocused = item.id === focusedItemId;

            return (
              <div
                key={item.id}
                ref={(el) => {
                  itemRefs.current[item.id] = el;
                }}
                className={`p-3.5 rounded-xl border transition-all ${
                  isFocused
                    ? 'border-primary ring-2 ring-primary/20 bg-primary/[0.03]'
                    : isSelected
                      ? 'border-primary/50 bg-primary/[0.02]'
                      : 'border-border bg-card'
                }`}
                data-testid={`needs-you-card-${item.id}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => toggleSelectItem(item.id)}
                      className="text-muted-foreground hover:text-foreground transition-colors"
                      aria-label="勾选条目"
                    >
                      {isSelected ? (
                        <CheckSquare className="w-3.5 h-3.5 text-primary" />
                      ) : (
                        <Square className="w-3.5 h-3.5" />
                      )}
                    </button>
                    <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-muted text-muted-foreground">
                      {getSourceIcon(item.source)}
                      <span>{getSourceBadgeLabel(item.source)}</span>
                    </span>
                    {item.urgency === 'urgent' && (
                      <span className="px-1.5 py-0.2 rounded text-[10px] font-medium bg-red-500/15 text-destructive">
                        紧急
                      </span>
                    )}
                  </div>

                  {item.agentName && (
                    <span className="text-[10px] text-muted-foreground font-mono">@{item.agentName}</span>
                  )}
                </div>

                <h3 className="mt-2 text-xs font-semibold text-foreground leading-snug">{item.title}</h3>

                <div className="mt-2 text-[11px] space-y-1.5 bg-muted/30 p-2.5 rounded-lg border border-border/40">
                  <div>
                    <span className="text-muted-foreground font-medium">为什么停: </span>
                    <span className="text-foreground/90">{item.whyStopped}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground font-medium">在等什么: </span>
                    <span className="text-amber-600 dark:text-amber-400 font-medium">{item.whatWaitingFor}</span>
                  </div>
                </div>

                <div className="mt-3 flex items-center justify-between gap-2 pt-2 border-t border-border/50">
                  <button
                    type="button"
                    onClick={() => onNavigateToDeepLink?.(item.deepLinkUrl, item)}
                    className="text-[11px] text-primary hover:underline flex items-center gap-1"
                    data-testid={`deep-link-btn-${item.id}`}
                  >
                    <span>定位至原消息</span>
                    <ExternalLink className="w-3 h-3" />
                  </button>

                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => openReasonModal(item.id)}
                      className="px-2.5 py-1 rounded text-[11px] border border-border text-muted-foreground hover:bg-muted transition-colors"
                      data-testid={`dismiss-btn-${item.id}`}
                    >
                      忽略
                    </button>
                    <button
                      type="button"
                      onClick={() => resolveInterruption(item.id)}
                      className="px-3 py-1 rounded text-[11px] bg-primary text-primary-foreground font-medium hover:bg-primary/90 transition-colors shadow-sm"
                      data-testid={`resolve-btn-${item.id}`}
                    >
                      批准 / 接手
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* 忽略理由输入模态弹窗（防止静默遗漏审计契约） */}
      {isReasonModalOpen && (
        <dialog
          open
          aria-labelledby="dismiss-reason-modal-title"
          className="fixed inset-0 z-[10000] flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm border-none m-0 w-full h-full max-w-none max-h-none"
          data-testid="dismiss-reason-modal"
        >
          <div className="w-full max-w-sm bg-background border border-border shadow-2xl rounded-2xl p-4">
            <h3 id="dismiss-reason-modal-title" className="text-xs font-semibold text-foreground">
              请输入忽略理由 (审计留痕)
            </h3>
            <p className="mt-1 text-[11px] text-muted-foreground">
              为了确保无人值守可信协同，忽略任何待办任务必须记录原因，防止静默丢单。
            </p>

            <textarea
              value={dismissReasonInput}
              onChange={(e) => {
                setDismissReasonInput(e.target.value);
                if (reasonError) {
                  setReasonError('');
                }
              }}
              placeholder="例如: 该步骤已被外部人工操作完成，无需重复执行..."
              rows={3}
              className="mt-3 w-full p-2.5 rounded-lg border border-border text-xs bg-muted/40 focus:outline-none focus:ring-1 focus:ring-primary"
              data-testid="dismiss-reason-textarea"
            />
            {reasonError && <p className="mt-1 text-[11px] text-destructive">{reasonError}</p>}

            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={closeReasonModal}
                className="px-3 py-1.5 rounded-lg border border-border text-xs text-muted-foreground hover:bg-muted"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleConfirmDismiss}
                className="px-3.5 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90"
                data-testid="confirm-dismiss-reason-btn"
              >
                确认忽略
              </button>
            </div>
          </div>
        </dialog>
      )}
    </aside>
  );
};
