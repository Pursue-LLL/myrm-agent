import React from 'react';
import {
  FolderGit2,
  FolderCode,
  GitBranch,
  Star,
  ChevronRight,
  Command,
  AlertCircle,
} from 'lucide-react';
import { useWorkspaceQuickSwitcherStore } from './useWorkspaceQuickSwitcherStore';

export interface WorkspaceBreadcrumbBarProps {
  className?: string;
  showShortcutBadge?: boolean;
}

export function WorkspaceBreadcrumbBar({
  className = '',
  showShortcutBadge = true,
}: WorkspaceBreadcrumbBarProps) {
  const workspaces = useWorkspaceQuickSwitcherStore((s) => s.workspaces);
  const currentWorkspaceId = useWorkspaceQuickSwitcherStore((s) => s.currentWorkspaceId);
  const openSwitcher = useWorkspaceQuickSwitcherStore((s) => s.openSwitcher);
  const toggleFavorite = useWorkspaceQuickSwitcherStore((s) => s.toggleFavorite);

  const currentWorkspace =
    workspaces.find((w) => w.id === currentWorkspaceId) ?? workspaces[0];

  if (!currentWorkspace) {
    return null;
  }

  const isGitRepo = Boolean(currentWorkspace.gitBranch);

  return (
    <nav
      aria-label="当前工作区导航与切换器"
      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs text-muted-foreground select-none ${className}`}
    >
      {/* 根空间标识 */}
      <div className="flex items-center gap-1 text-muted-foreground/80 font-medium">
        <span>工作区</span>
        <ChevronRight className="h-3 w-3 text-muted-foreground/40" />
      </div>

      {/* 当前工作区触发按钮 */}
      <button
        type="button"
        aria-label={`切换工作区，当前为 ${currentWorkspace.name}`}
        onClick={openSwitcher}
        className="group flex items-center gap-2 px-2 py-1 rounded-md bg-muted/40 hover:bg-muted text-foreground transition-colors border border-border/40 hover:border-border"
      >
        <span
          className={`flex h-4 w-4 items-center justify-center ${
            isGitRepo ? 'text-blue-500' : 'text-muted-foreground'
          }`}
        >
          {isGitRepo ? (
            <FolderGit2 className="h-3.5 w-3.5" />
          ) : (
            <FolderCode className="h-3.5 w-3.5" />
          )}
        </span>

        <span className="font-semibold text-xs tracking-tight truncate max-w-[160px]">
          {currentWorkspace.name}
        </span>

        {currentWorkspace.gitBranch && (
          <span className="hidden sm:inline-flex items-center gap-1 text-[11px] text-muted-foreground bg-background/50 px-1.5 py-0.5 rounded border border-border/30">
            <GitBranch className="h-2.5 w-2.5" />
            <span className="max-w-[80px] truncate">{currentWorkspace.gitBranch}</span>
          </span>
        )}

        {currentWorkspace.isDirty && (
          <span
            className="flex items-center text-amber-500"
            title={`${currentWorkspace.dirtyCount ?? 1} 处未提交修改`}
          >
            <AlertCircle className="h-3 w-3" />
          </span>
        )}

        {showShortcutBadge && (
          <span className="hidden md:inline-flex items-center gap-0.5 text-[10px] text-muted-foreground/70 bg-muted px-1 rounded border border-border/50">
            <Command className="h-2.5 w-2.5" />
            <span>O</span>
          </span>
        )}
      </button>

      {/* 快捷星标收藏当前工作区 */}
      <button
        type="button"
        aria-label={currentWorkspace.isFavorite ? '取消收藏当前工作区' : '星标收藏当前工作区'}
        onClick={() => {
          toggleFavorite(currentWorkspace.id);
        }}
        className={`p-1 rounded-md hover:bg-muted transition-colors ${
          currentWorkspace.isFavorite
            ? 'text-amber-500 fill-amber-500'
            : 'text-muted-foreground/60 hover:text-foreground'
        }`}
      >
        <Star
          className={`h-3.5 w-3.5 ${currentWorkspace.isFavorite ? 'fill-current' : ''}`}
        />
      </button>
    </nav>
  );
}
