/**
 * [INPUT]
 * ThreeCurrentsBoundary from workspaceBoundaryTypes.ts
 * [OUTPUT]
 * WorkspaceBoundaryHud: Top-level HUD displaying the 3 Currents execution boundary.
 * [POS]
 * src/components/features/workspace-boundary/WorkspaceBoundaryHud.tsx
 */

import React, { useState } from 'react';
import {
  Target,
  GitBranch,
  Laptop,
  Cloud,
  Cpu,
  RotateCw,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  AlertTriangle,
  FolderGit2,
} from 'lucide-react';
import { ThreeCurrentsBoundary } from './workspaceBoundaryTypes';

export interface WorkspaceBoundaryHudProps {
  boundary: ThreeCurrentsBoundary;
  onRefresh?: () => void;
  onOpenWorktreeMatrix?: () => void;
  onRequestSwitchProject?: () => void;
  className?: string;
}

export const WorkspaceBoundaryHud: React.FC<WorkspaceBoundaryHudProps> = ({
  boundary,
  onRefresh,
  onOpenWorktreeMatrix,
  onRequestSwitchProject,
  className = '',
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  const handleRefreshClick = async () => {
    if (onRefresh) {
      setIsRefreshing(true);
      try {
        await onRefresh();
      } finally {
        setIsRefreshing(false);
      }
    }
  };

  const renderHostIcon = () => {
    if (boundary.execution_host_type === 'cloud_sandbox') {
      return <Cloud className="w-3.5 h-3.5 text-sky-400" aria-label="Cloud Sandbox" />;
    }
    if (boundary.execution_host_type === 'docker_container') {
      return <Cpu className="w-3.5 h-3.5 text-indigo-400" aria-label="Docker Container" />;
    }
    return <Laptop className="w-3.5 h-3.5 text-emerald-400" aria-label="Local Host" />;
  };

  return (
    <div
      data-testid="workspace-boundary-hud"
      className={`bg-zinc-900/90 border border-zinc-800 rounded-lg p-2 text-xs font-mono select-none transition-all ${className}`}
    >
      {/* 3 Currents Capsules Row */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5 flex-1 min-w-0">
          {/* Current 1: Session & Goal */}
          <div
            data-testid="hud-capsule-session"
            className="flex items-center gap-1.5 bg-zinc-800/80 hover:bg-zinc-800 px-2.5 py-1 rounded-md border border-zinc-700/60 max-w-[280px] truncate"
            title={`Session Goal: ${boundary.session_goal || 'Maintain codebase tasks'}`}
          >
            <Target className="w-3.5 h-3.5 text-blue-400 shrink-0" />
            <span className="font-semibold text-zinc-200 truncate">
              {boundary.project_name || boundary.repo_name}
            </span>
            <span className="text-zinc-400 truncate">
              : {boundary.session_goal || 'Codebase tasks'}
            </span>
          </div>

          {/* Current 2: Working Directory & Git Branch */}
          <div
            data-testid="hud-capsule-git"
            className="flex items-center gap-1.5 bg-zinc-800/80 hover:bg-zinc-800 px-2.5 py-1 rounded-md border border-zinc-700/60"
            title={`CWD: ${boundary.cwd}`}
          >
            <GitBranch className="w-3.5 h-3.5 text-purple-400 shrink-0" />
            <span className="text-zinc-200 font-medium">
              {boundary.repo_name}
              <span className="text-zinc-400">
                {' '}
                [{boundary.git_branch}
                {boundary.git_worktree ? ` @ ${boundary.git_worktree}` : ''}]
              </span>
            </span>
            {boundary.git_is_clean ? (
              <span
                data-testid="git-status-clean"
                className="flex items-center text-emerald-400 gap-1 ml-1"
                title="Working tree clean"
              >
                <CheckCircle2 className="w-3 h-3" />
              </span>
            ) : (
              <span
                data-testid="git-status-dirty"
                className="flex items-center text-amber-400 gap-0.5 ml-1 bg-amber-950/40 px-1 py-0.2 rounded"
                title={`${boundary.git_uncommitted_changes} uncommitted changes`}
              >
                <AlertTriangle className="w-3 h-3" />
                <span className="text-[10px]">{boundary.git_uncommitted_changes}</span>
              </span>
            )}
          </div>

          {/* Current 3: Execution Host */}
          <div
            data-testid="hud-capsule-host"
            className="flex items-center gap-1.5 bg-zinc-800/80 hover:bg-zinc-800 px-2.5 py-1 rounded-md border border-zinc-700/60"
            title={`Host ID: ${boundary.execution_host_id}`}
          >
            {renderHostIcon()}
            <span className="text-zinc-200">{boundary.execution_host_label}</span>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-1 shrink-0">
          {onOpenWorktreeMatrix ? (
            <button
              type="button"
              data-testid="hud-worktree-matrix-btn"
              onClick={onOpenWorktreeMatrix}
              className="p-1 rounded text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition"
              title="Open Git Worktree Matrix"
            >
              <FolderGit2 className="w-3.5 h-3.5" />
            </button>
          ) : null}

          {onRefresh ? (
            <button
              type="button"
              data-testid="hud-refresh-btn"
              onClick={handleRefreshClick}
              disabled={isRefreshing}
              className={`p-1 rounded text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition ${
                isRefreshing ? 'animate-spin text-zinc-200' : ''
              }`}
              title="Re-probe execution boundary"
            >
              <RotateCw className="w-3.5 h-3.5" />
            </button>
          ) : null}

          <button
            type="button"
            data-testid="hud-expand-toggle-btn"
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 rounded text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition"
            title={isExpanded ? 'Collapse Details' : 'Expand Details'}
          >
            {isExpanded ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Expandable Inspector Panel */}
      {isExpanded ? (
        <div
          data-testid="hud-expanded-panel"
          className="mt-2 pt-2 border-t border-zinc-800/80 grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px] text-zinc-300"
        >
          <div className="space-y-1">
            <div className="text-zinc-400 flex items-center justify-between">
              <span>Absolute Working Directory:</span>
              {onRequestSwitchProject ? (
                <button
                  type="button"
                  data-testid="hud-switch-project-btn"
                  onClick={onRequestSwitchProject}
                  className="text-indigo-400 hover:text-indigo-300 underline text-[10px]"
                >
                  Switch Project
                </button>
              ) : null}
            </div>
            <div className="bg-zinc-950 p-1.5 rounded border border-zinc-800/50 break-all text-zinc-300">
              {boundary.cwd}
            </div>
          </div>

          <div className="space-y-1">
            <div className="text-zinc-400">Execution Topology & Probe:</div>
            <div className="bg-zinc-950 p-1.5 rounded border border-zinc-800/50 flex flex-col gap-0.5 text-zinc-300">
              <div className="flex justify-between">
                <span className="text-zinc-500">Host Topology:</span>
                <span className="text-zinc-200">{boundary.execution_host_type}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-500">Host Identifier:</span>
                <span className="text-zinc-200">{boundary.execution_host_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-500">Session ID:</span>
                <span className="text-zinc-400 truncate max-w-[150px]">
                  {boundary.session_id}
                </span>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};
