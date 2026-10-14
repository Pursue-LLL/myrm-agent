/**
 * [INPUT]
 * MultiRepoWorktreeEntry from workspaceBoundaryTypes.ts
 * [OUTPUT]
 * WorktreeMatrixNavigator: Matrix navigator for multi-repo and Git worktree branches.
 * [POS]
 * src/components/features/workspace-boundary/WorktreeMatrixNavigator.tsx
 */

import React from 'react';
import {
  FolderGit2,
  GitBranch,
  Folder,
  CheckCircle2,
  ArrowRight,
  X,
} from 'lucide-react';
import { MultiRepoWorktreeEntry } from './workspaceBoundaryTypes';

export interface WorktreeMatrixNavigatorProps {
  entries: MultiRepoWorktreeEntry[];
  onSelectWorktree: (entry: MultiRepoWorktreeEntry) => void;
  onClose?: () => void;
  className?: string;
}

export const WorktreeMatrixNavigator: React.FC<WorktreeMatrixNavigatorProps> = ({
  entries,
  onSelectWorktree,
  onClose,
  className = '',
}) => {
  return (
    <div
      data-testid="worktree-matrix-navigator"
      className={`bg-zinc-900 border border-zinc-700/80 rounded-xl p-4 shadow-xl text-xs font-mono space-y-3 ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <FolderGit2 className="w-4 h-4 text-purple-400" />
          <span className="font-semibold text-zinc-100 text-sm">
            Multi-Repo & Git Worktree Matrix
          </span>
        </div>
        {onClose ? (
          <button
            type="button"
            data-testid="worktree-matrix-close-btn"
            onClick={onClose}
            className="p-1 rounded text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition"
            title="Close Navigator"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        ) : null}
      </div>

      <p className="text-zinc-400 text-[11px] leading-relaxed">
        Matrix of workspace repositories and linked Git worktrees. Switch context cleanly without path confusion.
      </p>

      {/* Worktree entries list */}
      {entries.length === 0 ? (
        <div
          data-testid="worktree-empty-state"
          className="bg-zinc-950 p-4 rounded-lg text-center text-zinc-500 text-xs border border-zinc-800/60"
        >
          No linked Git worktrees found for current workspace.
        </div>
      ) : (
        <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
          {entries.map((entry, idx) => (
            <div
              key={`${entry.repo}-${entry.path}-${idx}`}
              data-testid={`worktree-entry-${idx}`}
              className={`p-3 rounded-lg border transition flex items-center justify-between gap-3 ${
                entry.is_active
                  ? 'bg-zinc-950 border-purple-500/60 shadow-sm'
                  : 'bg-zinc-950/70 border-zinc-800 hover:border-zinc-700 hover:bg-zinc-950'
              }`}
            >
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex items-center gap-2">
                  <GitBranch className="w-3.5 h-3.5 text-purple-400 shrink-0" />
                  <span className="font-semibold text-zinc-200 truncate">
                    {entry.branch}
                  </span>
                  {entry.worktree ? (
                    <span className="text-[10px] bg-zinc-800 px-1.5 py-0.2 rounded text-zinc-400">
                      Worktree: {entry.worktree}
                    </span>
                  ) : (
                    <span className="text-[10px] bg-zinc-800 px-1.5 py-0.2 rounded text-zinc-400">
                      Primary Repo
                    </span>
                  )}
                  {entry.is_active ? (
                    <span
                      data-testid="worktree-active-badge"
                      className="inline-flex items-center gap-0.5 text-[10px] text-emerald-400 bg-emerald-950/60 px-1.5 py-0.2 rounded border border-emerald-800/60"
                    >
                      <CheckCircle2 className="w-3 h-3" />
                      Active
                    </span>
                  ) : null}
                </div>

                <div className="flex items-center gap-1.5 text-zinc-500 text-[10px] truncate">
                  <Folder className="w-3 h-3 shrink-0" />
                  <span className="truncate font-mono">{entry.path}</span>
                </div>
              </div>

              {!entry.is_active ? (
                <button
                  type="button"
                  data-testid={`switch-worktree-btn-${idx}`}
                  onClick={() => onSelectWorktree(entry)}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition shrink-0"
                >
                  <span>Switch</span>
                  <ArrowRight className="w-3 h-3" />
                </button>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
