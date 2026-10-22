/**
 * [INPUT]
 * - react (POS: UI Framework)
 * - lucide-react (POS: Vector Icons)
 * - @/components/features/chat-window/workspace-breadcrumb/workspaceBreadcrumbTypes
 * - @/components/features/chat-window/workspace-breadcrumb/workspaceBreadcrumbEngine
 * - @/components/features/chat-window/workspace-breadcrumb/useWorkspaceBreadcrumbStore
 *
 * [OUTPUT]
 * - WorkspaceBreadcrumbBar (POS: Top bar breadcrumb component displaying physical workspace path & reveal actions)
 *
 * [POS]
 * Visual presentation bar for Item 197 (P1): WorkspaceBreadcrumbPathAndDesktopRevealSuite.
 * Renders structured breadcrumb segments, sandbox status badge, one-click clipboard copy,
 * and desktop Finder / Terminal bridge triggers to eliminate artifact landing blind spots.
 */

import React, { useMemo, useState } from 'react';
import {
  Folder,
  Box,
  ChevronRight,
  Copy,
  Check,
  ExternalLink,
  Terminal,
} from 'lucide-react';
import {
  parseWorkspacePath,
  truncatePathSegments,
} from './workspaceBreadcrumbEngine';
import { useWorkspaceBreadcrumbStore } from './useWorkspaceBreadcrumbStore';

export interface WorkspaceBreadcrumbBarProps {
  readonly chatId?: string;
  readonly overridePath?: string;
  readonly maxVisibleSegments?: number;
  readonly className?: string;
}

export const WorkspaceBreadcrumbBar: React.FC<WorkspaceBreadcrumbBarProps> = ({
  chatId,
  overridePath,
  maxVisibleSegments = 4,
  className = '',
}) => {
  const store = useWorkspaceBreadcrumbStore();
  const [justCopied, setJustCopied] = useState(false);

  const activePath = useMemo(() => {
    if (overridePath) {
      return overridePath;
    }
    if (chatId && store.workspacePathByChatId[chatId]) {
      return store.workspacePathByChatId[chatId];
    }
    return store.getCurrentPath();
  }, [overridePath, chatId, store]);

  const locationInfo = useMemo(() => {
    return parseWorkspacePath(activePath);
  }, [activePath]);

  const visibleSegments = useMemo(() => {
    return truncatePathSegments(locationInfo.segments, maxVisibleSegments);
  }, [locationInfo.segments, maxVisibleSegments]);

  const handleCopy = async () => {
    await store.copyCurrentPath(activePath);
    setJustCopied(true);
    setTimeout(() => {
      setJustCopied(false);
      store.resetCopied();
    }, 2000);
  };

  const handleRevealFinder = () => {
    store.revealInFinder(activePath);
  };

  const handleRevealTerminal = () => {
    store.revealInTerminal(activePath);
  };

  const revealLabel = locationInfo.platform === 'darwin' ? '在访达中定位' : '在资源管理器定位';

  return (
    <div
      data-testid="workspace-breadcrumb-bar"
      className={`flex items-center justify-between gap-3 px-3 py-1.5 bg-slate-900/80 border border-slate-800 rounded-lg text-xs text-slate-300 backdrop-blur-sm ${className}`}
    >
      {/* 路径与环境标识区 */}
      <div className="flex items-center gap-2 overflow-x-auto min-w-0 flex-1 scrollbar-none">
        <span
          data-testid="workspace-badge"
          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0 ${
            locationInfo.isSandbox
              ? 'bg-amber-950/60 text-amber-300 border border-amber-800/60'
              : 'bg-emerald-950/60 text-emerald-300 border border-emerald-800/60'
          }`}
        >
          {locationInfo.isSandbox ? (
            <>
              <Box className="w-3 h-3" />
              <span>沙箱隔离</span>
            </>
          ) : (
            <>
              <Folder className="w-3 h-3" />
              <span>物理工作区</span>
            </>
          )}
        </span>

        {/* 分段面包屑 */}
        <nav
          aria-label="工作区面包屑"
          className="flex items-center gap-1 truncate font-mono text-[11px]"
        >
          {visibleSegments.map((segment, index) => {
            const isLast = index === visibleSegments.length - 1;
            return (
              <React.Fragment key={`${segment.fullPath}-${segment.name}-${index}`}>
                {index > 0 && (
                  <ChevronRight className="w-3 h-3 text-slate-600 shrink-0" />
                )}
                <span
                  data-testid={`breadcrumb-segment-${index}`}
                  title={segment.fullPath}
                  className={`truncate ${
                    isLast
                      ? 'text-cyan-300 font-semibold max-w-[180px]'
                      : 'text-slate-400 hover:text-slate-200 transition-colors max-w-[120px]'
                  }`}
                >
                  {segment.name}
                </span>
              </React.Fragment>
            );
          })}
        </nav>
      </div>

      {/* 动作按钮区 */}
      <div className="flex items-center gap-1 shrink-0">
        <button
          type="button"
          onClick={handleCopy}
          data-testid="btn-copy-path"
          aria-label="复制绝对路径"
          title="复制物理绝对路径"
          className="p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors focus:outline-none focus:ring-1 focus:ring-cyan-500"
        >
          {justCopied ? (
            <Check className="w-3.5 h-3.5 text-emerald-400" />
          ) : (
            <Copy className="w-3.5 h-3.5" />
          )}
        </button>

        <button
          type="button"
          onClick={handleRevealFinder}
          data-testid="btn-reveal-finder"
          aria-label={revealLabel}
          title={revealLabel}
          className="p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors focus:outline-none focus:ring-1 focus:ring-cyan-500"
        >
          <ExternalLink className="w-3.5 h-3.5" />
        </button>

        <button
          type="button"
          onClick={handleRevealTerminal}
          data-testid="btn-reveal-terminal"
          aria-label="在终端中打开"
          title="在系统终端打开此目录"
          className="p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors focus:outline-none focus:ring-1 focus:ring-cyan-500"
        >
          <Terminal className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
};
