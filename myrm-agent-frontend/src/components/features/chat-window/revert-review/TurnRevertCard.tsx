/**
 * [INPUT]
 * - ./revertReviewTypes::TurnFileChange, TurnRevertStatus
 * - ./useTurnRevertReviewStore::useTurnRevertReviewStore
 * - lucide-react::Undo2, FileCode, Check, AlertTriangle, ChevronDown, ChevronRight, SplitSquareHorizontal, RefreshCw
 *
 * [OUTPUT]
 * - TurnRevertCard: 会话流单轮文件改动摘要与一键安全撤销卡片组件
 *
 * [POS]
 * 会话流中挂载在智能体回复底部的单轮文件变动汇总与原子级回滚控制卡片。
 */

'use client';

import React, { useState, useMemo, useCallback } from 'react';
import {
  Undo2,
  FileCode,
  Check,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  SplitSquareHorizontal,
  RefreshCw,
} from 'lucide-react';
import type { TurnFileChange, TurnFileOperation } from './revertReviewTypes';
import { useTurnRevertReviewStore } from './useTurnRevertReviewStore';

export interface TurnRevertCardProps {
  sessionId: string;
  messageId: string;
  changes: TurnFileChange[];
  onOpenDiff?: (filePath?: string) => void;
  className?: string;
}

function getOperationBadge(op: TurnFileOperation): { label: string; className: string } {
  switch (op) {
    case 'create':
      return { label: '新增', className: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20' };
    case 'delete':
      return { label: '删除', className: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20' };
    case 'update':
    default:
      return { label: '修改', className: 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20' };
  }
}

export const TurnRevertCard: React.FC<TurnRevertCardProps> = ({
  sessionId,
  messageId,
  changes,
  onOpenDiff,
  className = '',
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  const revertState = useTurnRevertReviewStore((s) => s.revertStates[messageId]);
  const revertTurn = useTurnRevertReviewStore((s) => s.revertTurn);
  const openDiff = useTurnRevertReviewStore((s) => s.openDiff);

  const status = revertState?.status || 'idle';
  const isReverted = status === 'success';

  const { totalAdditions, totalDeletions, revertibleCount, nonRevertibleCount } = useMemo(() => {
    let adds = 0;
    let dels = 0;
    let revCount = 0;
    let nonRevCount = 0;

    for (const change of changes) {
      adds += change.additions ?? 0;
      dels += change.deletions ?? 0;
      if (change.revertible === false) {
        nonRevCount += 1;
      } else {
        revCount += 1;
      }
    }
    return {
      totalAdditions: adds,
      totalDeletions: dels,
      revertibleCount: revCount,
      nonRevertibleCount: nonRevCount,
    };
  }, [changes]);

  const handleConfirmRevert = useCallback(async () => {
    const success = await revertTurn(sessionId, messageId);
    if (success) {
      setShowConfirmDialog(false);
    }
  }, [revertTurn, sessionId, messageId]);

  const handleOpenDiffView = useCallback(
    (filePath?: string) => {
      openDiff(sessionId, messageId);
      if (onOpenDiff) {
        onOpenDiff(filePath);
      }
    },
    [openDiff, sessionId, messageId, onOpenDiff]
  );

  if (changes.length === 0) {
    return null;
  }

  return (
    <section
      aria-label="单轮文件改动摘要与撤销卡片"
      className={`rounded-lg border border-border/70 bg-card/60 p-2.5 text-xs text-card-foreground shadow-xs backdrop-blur-xs transition-all ${className}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => {
            setIsExpanded((prev) => !prev);
          }}
          className="flex items-center gap-1.5 font-medium hover:text-foreground text-muted-foreground transition-colors"
          aria-expanded={isExpanded}
          aria-label={isExpanded ? '收起文件变更列表' : '展开文件变更列表'}
        >
          {isExpanded ? (
            <ChevronDown className="w-3.5 h-3.5" aria-hidden="true" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5" aria-hidden="true" />
          )}
          <FileCode className="w-3.5 h-3.5 text-primary" aria-hidden="true" />
          <span>
            已修改 {changes.length} 个文件
          </span>
          {(totalAdditions > 0 || totalDeletions > 0) && (
            <span className="flex items-center gap-1 text-[11px] font-mono ml-1 font-normal">
              {totalAdditions > 0 && (
                <span className="text-emerald-600 dark:text-emerald-400">+{totalAdditions}</span>
              )}
              {totalDeletions > 0 && (
                <span className="text-rose-600 dark:text-rose-400">-{totalDeletions}</span>
              )}
            </span>
          )}
        </button>

        <div className="flex items-center gap-1.5 ml-auto">
          <button
            type="button"
            onClick={() => {
              handleOpenDiffView();
            }}
            className="inline-flex items-center gap-1 px-2 py-1 rounded bg-muted/80 hover:bg-muted text-foreground text-[11px] font-medium transition-colors border border-border/40"
            aria-label="查看完整 Diff 视图"
          >
            <SplitSquareHorizontal className="w-3 h-3" aria-hidden="true" />
            <span>审查 Diff</span>
          </button>

          {isReverted ? (
            <span className="inline-flex items-center gap-1 px-2 py-1 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[11px] font-medium border border-emerald-500/20">
              <Check className="w-3 h-3" aria-hidden="true" />
              <span>已成功撤销</span>
            </span>
          ) : (
            <button
              type="button"
              onClick={() => {
                setShowConfirmDialog(true);
              }}
              disabled={status === 'loading' || revertibleCount === 0}
              className="inline-flex items-center gap-1 px-2 py-1 rounded bg-amber-500/10 hover:bg-amber-500/20 text-amber-700 dark:text-amber-400 text-[11px] font-medium transition-colors border border-amber-500/30 disabled:opacity-50"
              aria-label="一键撤销本轮文件改动"
            >
              {status === 'loading' ? (
                <RefreshCw className="w-3 h-3 animate-spin" aria-hidden="true" />
              ) : (
                <Undo2 className="w-3 h-3" aria-hidden="true" />
              )}
              <span>撤销本轮修改</span>
            </button>
          )}
        </div>
      </div>

      {isExpanded && (
        <ul className="mt-2.5 space-y-1 pt-2 border-t border-border/40 font-mono text-[11px]">
          {changes.map((change) => {
            const badge = getOperationBadge(change.operation);
            const fileName = change.path.split('/').pop() || change.path;
            return (
              <li
                key={change.path}
                className="flex items-center justify-between gap-2 px-1.5 py-1 rounded hover:bg-muted/50 transition-colors"
              >
                <div className="flex items-center gap-1.5 truncate">
                  <span
                    className={`px-1 py-0.2 rounded border text-[10px] font-sans font-medium ${badge.className}`}
                  >
                    {badge.label}
                  </span>
                  <span className="truncate text-foreground" title={change.path}>
                    {fileName}
                  </span>
                  <span className="text-muted-foreground/70 truncate text-[10px]">
                    {change.path}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {change.revertible === false && (
                    <span className="text-[10px] text-amber-600 dark:text-amber-400 flex items-center gap-0.5">
                      <AlertTriangle className="w-2.5 h-2.5" aria-hidden="true" />
                      <span>不可回滚</span>
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      handleOpenDiffView(change.path);
                    }}
                    className="text-[10px] text-primary hover:underline"
                  >
                    Diff
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {showConfirmDialog && (
        <dialog
          open
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs border-0 w-full h-full"
        >
          <div
            role="document"
            className="w-full max-w-sm rounded-lg border border-border bg-background p-4 shadow-xl text-left"
          >
            <div className="flex items-center gap-2 mb-2">
              <div className="p-1.5 rounded-full bg-amber-500/10 text-amber-600">
                <AlertTriangle className="w-4 h-4" aria-hidden="true" />
              </div>
              <h3 className="text-sm font-semibold text-foreground">确认撤销本轮文件改动？</h3>
            </div>
            <p className="text-xs text-muted-foreground mb-3 leading-relaxed">
              将根据执行前快照原子还原 {revertibleCount} 个修改过的文件。
              {nonRevertibleCount > 0 && (
                <span className="block mt-1 text-amber-600 dark:text-amber-400 font-medium">
                  注意：存在 {nonRevertibleCount} 个文件因超限无法自动回滚，将被保留。
                </span>
              )}
            </p>
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setShowConfirmDialog(false);
                }}
                disabled={status === 'loading'}
                className="px-3 py-1.5 rounded text-xs text-muted-foreground hover:bg-muted transition-colors"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => {
                  void handleConfirmRevert();
                }}
                disabled={status === 'loading'}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-rose-600 text-white text-xs font-medium hover:bg-rose-700 transition-colors shadow-xs"
              >
                {status === 'loading' && (
                  <RefreshCw className="w-3 h-3 animate-spin" aria-hidden="true" />
                )}
                <span>确认还原</span>
              </button>
            </div>
          </div>
        </dialog>
      )}
    </section>
  );
};
