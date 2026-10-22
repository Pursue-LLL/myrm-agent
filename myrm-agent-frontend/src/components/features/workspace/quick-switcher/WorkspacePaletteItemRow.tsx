import React from 'react';
import {
  FolderGit2,
  FolderCode,
  GitBranch,
  AlertCircle,
  Star,
  ExternalLink,
  MessageSquare,
  FileCode2,
  Check,
} from 'lucide-react';
import type { WorkspaceItem } from './workspaceQuickSwitcherTypes';
import { REVEAL_ON_HOVER } from '@/lib/utils/a11y';

export interface WorkspacePaletteItemRowProps {
  workspace: WorkspaceItem;
  isSelected: boolean;
  isCurrent: boolean;
  onSelect: () => void;
  onToggleFavorite: (e: React.MouseEvent) => void;
  onOpenInNewTab: (e: React.MouseEvent) => void;
}

export function WorkspacePaletteItemRow({
  workspace,
  isSelected,
  isCurrent,
  onSelect,
  onToggleFavorite,
  onOpenInNewTab,
}: WorkspacePaletteItemRowProps) {
  const isGitRepo = Boolean(workspace.gitBranch);

  return (
    <div
      data-testid="workspace-palette-row"
      data-selected={isSelected}
      className={`group relative flex items-center justify-between px-3.5 py-2.5 rounded-lg transition-colors text-sm border outline-none focus-visible:ring-2 focus-visible:ring-ring select-none ${
        isSelected
          ? 'bg-accent/80 border-accent-foreground/20 text-accent-foreground shadow-sm'
          : 'bg-card/40 border-transparent text-card-foreground hover:bg-muted/50'
      }`}
    >
      {/* 左侧：点击切换工作区的主交互按钮 */}
      <button
        type="button"
        onClick={onSelect}
        className="flex items-center gap-3 min-w-0 flex-1 mr-3 text-left bg-transparent border-0 p-0 cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
      >
        <div
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md border ${
            isGitRepo
              ? 'bg-blue-500/10 border-blue-500/20 text-blue-500'
              : 'bg-muted border-border/50 text-muted-foreground'
          }`}
        >
          {isGitRepo ? (
            <FolderGit2 className="h-4.5 w-4.5" />
          ) : (
            <FolderCode className="h-4.5 w-4.5" />
          )}
        </div>

        <div className="flex flex-col min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium truncate text-foreground">{workspace.name}</span>
            {isCurrent && (
              <span className="inline-flex items-center gap-1 rounded bg-primary/10 px-1.5 py-0.5 text-[11px] font-medium text-primary">
                <Check className="h-3 w-3" />
                当前工作区
              </span>
            )}
            {workspace.isDirty && (
              <span
                className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-1.5 py-0.5 text-[11px] font-medium text-amber-600 dark:text-amber-400"
                title={`${workspace.dirtyCount ?? 1} 处未提交修改`}
              >
                <AlertCircle className="h-3 w-3" />
                <span>{workspace.dirtyCount ?? 1} 变更</span>
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 mt-0.5">
            <span
              className="text-xs text-muted-foreground truncate max-w-[280px]"
              title={workspace.path}
            >
              {workspace.path}
            </span>
            {workspace.rulesLoaded.length > 0 && (
              <div className="hidden sm:flex items-center gap-1 text-[11px] text-muted-foreground">
                <FileCode2 className="h-3 w-3" />
                <span>{workspace.rulesLoaded.slice(0, 2).join(', ')}</span>
                {workspace.rulesLoaded.length > 2 && (
                  <span>+{workspace.rulesLoaded.length - 2}</span>
                )}
              </div>
            )}
          </div>
        </div>
      </button>

      {/* 右侧：Git分支 + 会话数 + 快捷操作 */}
      <div className="flex items-center gap-2 shrink-0">
        {workspace.gitBranch && (
          <span className="hidden md:inline-flex items-center gap-1 rounded border border-border/60 bg-muted/30 px-2 py-0.5 text-xs text-muted-foreground">
            <GitBranch className="h-3 w-3" />
            <span className="max-w-[100px] truncate">{workspace.gitBranch}</span>
          </span>
        )}

        {workspace.activeSessionsCount > 0 && (
          <span
            className="hidden sm:inline-flex items-center gap-1 rounded bg-secondary px-1.5 py-0.5 text-xs text-secondary-foreground"
            title={`${workspace.activeSessionsCount} 个活跃会话`}
          >
            <MessageSquare className="h-3 w-3" />
            <span>{workspace.activeSessionsCount}</span>
          </span>
        )}

        {/* 收藏按钮 */}
        <button
          type="button"
          aria-label={workspace.isFavorite ? '取消收藏工作区' : '收藏工作区'}
          onClick={onToggleFavorite}
          className={`p-1.5 rounded-md hover:bg-muted transition-colors ${
            workspace.isFavorite
              ? 'text-amber-500 fill-amber-500'
              : 'text-muted-foreground/60 hover:text-foreground'
          }`}
        >
          <Star
            className={`h-4 w-4 ${workspace.isFavorite ? 'fill-current' : ''}`}
          />
        </button>

        {/* 在新独立窗口打开 */}
        <button
          type="button"
          aria-label="在新窗口打开工作区"
          onClick={onOpenInNewTab}
          className={`p-1.5 rounded-md text-muted-foreground/60 hover:text-foreground hover:bg-muted transition-colors ${REVEAL_ON_HOVER}`}
          title="在新窗口打开 (⌘↵)"
        >
          <ExternalLink className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
