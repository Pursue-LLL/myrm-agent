/**
 * [INPUT]
 * - react (POS: UI Framework)
 * - lucide-react (POS: Vector Icons)
 * - @/components/features/chat-window/session-branch-archive/sessionBranchArchiveTypes
 * - @/components/features/chat-window/session-branch-archive/useSessionBranchArchiveStore
 *
 * [OUTPUT]
 * - SessionRuleAnchorHeader (POS: Header bar indicating permanent rule anchorage and /new archive triggers)
 *
 * [POS]
 * Visual reassurance header for Item 200 (P1): SessionBranchArchiveAndRulePreservedResetSuite.
 * Visually separates "Rules in Files" from "Process in Session", eliminating user fear of context loss
 * and providing one-click clean restarts (/new) and branch exploration entry points.
 */

import React from 'react';
import {
  Anchor,
  Archive,
  GitFork,
  History,
  Sparkles,
} from 'lucide-react';
import { useSessionBranchArchiveStore } from './useSessionBranchArchiveStore';

export interface SessionRuleAnchorHeaderProps {
  readonly onArchiveReset?: () => void;
  readonly onForkBranch?: () => void;
  readonly currentTokenCount?: number;
  readonly currentMessageCount?: number;
  readonly className?: string;
}

export const SessionRuleAnchorHeader: React.FC<SessionRuleAnchorHeaderProps> = ({
  onArchiveReset,
  onForkBranch,
  currentTokenCount = 0,
  currentMessageCount = 0,
  className = '',
}) => {
  const {
    currentRuleHash,
    snapshots,
    archiveAndResetSession,
    forkBranchFromMessage,
    setArchiveModalOpen,
  } = useSessionBranchArchiveStore();

  const handleArchiveAndReset = () => {
    archiveAndResetSession({
      title: `会话阶段性归档 (${new Date().toLocaleTimeString()})`,
      messageCount: currentMessageCount,
      totalTokens: currentTokenCount,
      summary: '阶段性任务完成，归档过程并以纯净规则重新起航。',
    });

    if (onArchiveReset) {
      onArchiveReset();
    }
  };

  const handleFork = () => {
    forkBranchFromMessage(`msg-checkpoint-${Date.now()}`, '探索分支');
    if (onForkBranch) {
      onForkBranch();
    }
  };

  const handleOpenModal = () => {
    setArchiveModalOpen(true);
  };

  const snapshotCount = snapshots.length;

  return (
    <div
      data-testid="session-rule-anchor-header"
      className={`flex items-center justify-between gap-3 px-3 py-1.5 bg-slate-900/90 border border-slate-800 rounded-lg text-xs text-slate-300 backdrop-blur-sm ${className}`}
    >
      {/* 左侧：“规矩放文件”恒常锚定指示 */}
      <div className="flex items-center gap-2 min-w-0">
        <span
          data-testid="rule-anchor-badge"
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-cyan-950/70 text-cyan-300 border border-cyan-800/60 shrink-0"
        >
          <Anchor className="w-3.5 h-3.5 text-cyan-400" />
          <span>规矩放文件：项目规则已永久锚定</span>
        </span>

        <span
          data-testid="rule-version-hash"
          title="当前生效的全局规则指纹"
          className="hidden sm:inline font-mono text-[10px] text-slate-500 truncate"
        >
          AGENTS.md #{currentRuleHash}
        </span>
      </div>

      {/* 右侧：动作控制区 */}
      <div className="flex items-center gap-1.5 shrink-0">
        {/* 派生分支按钮 */}
        <button
          type="button"
          data-testid="btn-fork-branch"
          aria-label="从当前节点派生探索分支"
          title="从当前会话节点派生新分支 (/fork)"
          onClick={handleFork}
          className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium text-slate-400 bg-slate-800/60 border border-slate-700/60 hover:text-slate-100 hover:bg-slate-800 transition-colors"
        >
          <GitFork className="w-3 h-3 text-purple-400" />
          <span>/fork</span>
        </button>

        {/* 历史归档快照抽屉按钮 */}
        <button
          type="button"
          data-testid="btn-view-snapshots"
          aria-label="查看历史会话归档快照"
          title="查看只读历史归档会话"
          onClick={handleOpenModal}
          className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium text-slate-400 bg-slate-800/60 border border-slate-700/60 hover:text-slate-100 hover:bg-slate-800 transition-colors"
        >
          <History className="w-3 h-3 text-amber-400" />
          <span>归档快照 ({snapshotCount})</span>
        </button>

        {/* 归档并纯净重启 (/new) */}
        <button
          type="button"
          data-testid="btn-archive-reset"
          aria-label="归档当前会话并开启纯净新会话"
          title="将当前过程转为只读快照存档，并带规纯净重启 (/new 优于 /compact)"
          onClick={handleArchiveAndReset}
          className="flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-medium bg-emerald-950/70 text-emerald-300 border border-emerald-800/60 hover:bg-emerald-900/60 transition-colors shadow-sm"
        >
          <Archive className="w-3 h-3" />
          <Sparkles className="w-3 h-3 text-emerald-400" />
          <span>归档并重启 (/new)</span>
        </button>
      </div>
    </div>
  );
};
