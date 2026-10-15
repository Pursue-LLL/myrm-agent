/**
 * [INPUT]
 * - react (POS: UI Framework)
 * - lucide-react (POS: Vector Icons)
 * - @/components/features/chat-window/session-branch-archive/sessionBranchArchiveTypes
 * - @/components/features/chat-window/session-branch-archive/sessionBranchArchiveEngine
 * - @/components/features/chat-window/session-branch-archive/useSessionBranchArchiveStore
 *
 * [OUTPUT]
 * - SessionBranchArchiveModal (POS: Dialog modal displaying archived snapshots and branch tree exploration)
 *
 * [POS]
 * Management modal for Item 200 (P1): SessionBranchArchiveAndRulePreservedResetSuite.
 * Renders read-only snapshots, branch tree navigation, token hygiene metrics,
 * and allows users to inspect or remove historic milestone archives.
 */

import React, { useMemo } from 'react';
import {
  Archive,
  GitBranch,
  Trash2,
  X,
  Clock,
  Coins,
  ShieldCheck,
  CheckCircle2,
} from 'lucide-react';
import {
  calculateContextHygiene,
  flattenBranchTree,
} from './sessionBranchArchiveEngine';
import { useSessionBranchArchiveStore } from './useSessionBranchArchiveStore';

export interface SessionBranchArchiveModalProps {
  readonly onClose?: () => void;
  readonly className?: string;
}

export const SessionBranchArchiveModal: React.FC<SessionBranchArchiveModalProps> = ({
  onClose,
  className = '',
}) => {
  const {
    isArchiveModalOpen,
    snapshots,
    branchRoot,
    activeBranchId,
    setArchiveModalOpen,
    removeSnapshot,
    switchActiveBranch,
  } = useSessionBranchArchiveStore();

  const handleClose = () => {
    setArchiveModalOpen(false);
    if (onClose) {
      onClose();
    }
  };

  const branches = useMemo(() => {
    return flattenBranchTree(branchRoot);
  }, [branchRoot]);

  const totalTokensSaved = useMemo(() => {
    return snapshots.reduce((acc, s) => {
      const hygiene = calculateContextHygiene(s.totalTokens);
      return acc + hygiene.tokensSaved;
    }, 0);
  }, [snapshots]);

  if (!isArchiveModalOpen) {
    return null;
  }

  return (
    <dialog
      open
      aria-modal="true"
      data-testid="session-branch-archive-modal"
      className={`fixed inset-0 z-50 flex items-center justify-center p-4 bg-transparent border-none ${className}`}
    >
      {/* 语义化背景遮罩按钮 */}
      <button
        type="button"
        data-testid="modal-backdrop"
        aria-label="关闭归档快照遮罩"
        onClick={handleClose}
        className="fixed inset-0 bg-black/70 backdrop-blur-sm -z-10 focus:outline-none"
      />

      <div className="relative z-10 w-full max-w-2xl max-h-[85vh] flex flex-col rounded-xl bg-slate-900 border border-slate-800 text-slate-100 shadow-2xl overflow-hidden animate-fadeIn">
        {/* 顶部标题栏 */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800 bg-slate-950/60 shrink-0">
          <div className="flex items-center gap-2">
            <Archive className="w-4 h-4 text-emerald-400" />
            <h2 className="text-sm font-semibold text-slate-200">
              会话分支归档与规矩恒常重置看板
            </h2>
          </div>

          <button
            type="button"
            data-testid="btn-close-modal"
            aria-label="关闭弹窗"
            onClick={handleClose}
            className="p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 哲学与上下文卫生指标横幅 */}
        <div className="px-5 py-2.5 bg-slate-950/40 border-b border-slate-800/80 flex items-center justify-between text-xs text-slate-400 shrink-0">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-cyan-400 shrink-0" />
            <span>规矩放文件，过程放会话 · /new 优于劣质 /compact</span>
          </div>

          <div className="flex items-center gap-1 font-mono text-[11px] text-emerald-400">
            <Coins className="w-3.5 h-3.5" />
            <span>累计轻装节约 Token：~{totalTokensSaved.toLocaleString()}</span>
          </div>
        </div>

        {/* 主体内容滚动区 */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4 scrollbar-thin">
          {/* 分支树探索卡片区 */}
          {branches.length > 0 && (
            <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 space-y-2">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-purple-300">
                <GitBranch className="w-3.5 h-3.5" />
                <span>会话探索分支树 (Branch Tree)</span>
              </div>

              <div className="flex flex-wrap gap-2">
                {branches.map((b) => {
                  const isActive = b.id === activeBranchId;
                  return (
                    <button
                      key={b.id}
                      type="button"
                      data-testid={`branch-node-${b.id}`}
                      onClick={() => switchActiveBranch(b.id)}
                      className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium border transition-colors ${
                        isActive
                          ? 'bg-purple-950/80 text-purple-200 border-purple-700/80 shadow-sm'
                          : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200 hover:bg-slate-800'
                      }`}
                    >
                      {isActive && <CheckCircle2 className="w-3 h-3 text-purple-400" />}
                      <span>{b.title}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* 归档快照列表 */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-amber-400" />
              <span>历史阶段性归档快照 ({snapshots.length})</span>
            </h3>

            {snapshots.length === 0 ? (
              <div
                data-testid="snapshots-empty-hint"
                className="p-8 text-center rounded-lg border border-dashed border-slate-800 text-slate-500 text-xs"
              >
                暂无归档快照。在长任务阶段性完成或 Token 逼近高位时，点击顶栏【归档并重启 (/new)】即可保存只读快照。
              </div>
            ) : (
              <div className="space-y-2">
                {snapshots.map((s) => (
                  <div
                    key={s.id}
                    data-testid={`snapshot-item-${s.id}`}
                    className="flex items-center justify-between p-3 rounded-lg bg-slate-950/70 border border-slate-800 hover:border-slate-700 transition-colors"
                  >
                    <div className="flex flex-col min-w-0 pr-3">
                      <span className="text-xs font-medium text-slate-200 truncate">
                        {s.title}
                      </span>
                      {s.summary && (
                        <span className="text-[11px] text-slate-400 truncate">
                          {s.summary}
                        </span>
                      )}
                      <div className="flex items-center gap-3 mt-1 text-[10px] font-mono text-slate-500">
                        <span>{s.messageCount} 条消息</span>
                        <span>{s.totalTokens.toLocaleString()} tokens</span>
                        <span>规则指纹 #{s.ruleHash}</span>
                        <span>{new Date(s.archivedAt).toLocaleTimeString()}</span>
                      </div>
                    </div>

                    <button
                      type="button"
                      data-testid={`btn-remove-snapshot-${s.id}`}
                      aria-label="删除快照"
                      title="删除此历史归档快照"
                      onClick={() => removeSnapshot(s.id)}
                      className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-slate-800 transition-colors shrink-0"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </dialog>
  );
};
