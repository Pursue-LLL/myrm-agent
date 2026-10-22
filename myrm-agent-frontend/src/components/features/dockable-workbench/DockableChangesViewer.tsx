import React, { useState, useMemo } from 'react';
import {
  GitCommit,
  GitPullRequest,
  FileCode,
  Plus,
  Minus,
  ExternalLink,
} from 'lucide-react';
import { useDockableWorkbenchStore } from './useDockableWorkbenchStore';
import { computeDiffStats } from './dockableWorkbenchEngine';
import type { FileChangeItem } from './dockableWorkbenchTypes';

export interface DockableChangesViewerProps {
  readonly className?: string;
  readonly onCreatePR?: () => void;
}

export const DockableChangesViewer: React.FC<DockableChangesViewerProps> = ({
  className = '',
  onCreatePR,
}) => {
  const changesList = useDockableWorkbenchStore((state) => {
    return state.changesList;
  });

  const [selectedFilePath, setSelectedFilePath] = useState<string>(
    changesList[0]?.path ?? ''
  );

  const stats = useMemo(() => {
    return computeDiffStats(changesList);
  }, [changesList]);

  const activeChange: FileChangeItem | undefined = useMemo(() => {
    return (
      changesList.find((c) => {
        return c.path === selectedFilePath;
      }) ?? changesList[0]
    );
  }, [changesList, selectedFilePath]);

  return (
    <div
      data-testid="dockable-changes-viewer"
      className={`flex flex-col h-full rounded-xl border border-slate-800 bg-slate-950/80 p-3.5 text-slate-100 ${className}`}
    >
      {/* 头部摘要与 PR 触发 */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <GitCommit className="h-4 w-4 text-indigo-400" />
          <span className="text-xs font-semibold text-slate-200">
            沙箱代码变更（Changes 只读观察）
          </span>
          <span className="text-[10px] text-slate-400">
            {stats.changedFilesCount} 个文件
          </span>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 text-[11px] font-mono">
            <span className="flex items-center text-emerald-400">
              <Plus className="h-3 w-3" />
              {stats.totalAdditions}
            </span>
            <span className="flex items-center text-rose-400">
              <Minus className="h-3 w-3" />
              {stats.totalDeletions}
            </span>
          </div>

          <button
            type="button"
            onClick={onCreatePR}
            className="flex items-center gap-1 rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-2.5 py-1 text-xs font-medium text-indigo-300 hover:bg-indigo-500/20 transition-colors"
          >
            <span>在 GitHub 提 PR</span>
            <ExternalLink className="h-3 w-3" />
          </button>
        </div>
      </div>

      {/* 文件列表与 Diff Hunk 分栏视图 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 my-3 flex-1 min-h-48 overflow-hidden">
        {/* 左侧文件列表 */}
        <div className="md:col-span-1 space-y-1.5 overflow-y-auto pr-1">
          {changesList.map((item) => {
            const isSelected = (activeChange?.path ?? '') === item.path;
            return (
              <button
                key={item.path}
                type="button"
                onClick={() => {
                  setSelectedFilePath(item.path);
                }}
                className={`w-full text-left rounded-lg p-2 transition-all ${
                  isSelected
                    ? 'border border-indigo-500/60 bg-indigo-950/30 text-white'
                    : 'border border-slate-800/80 bg-slate-900/40 text-slate-400 hover:bg-slate-800/50'
                }`}
              >
                <div className="flex items-center gap-1.5 text-xs truncate font-medium">
                  <FileCode className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                  <span className="truncate">{item.path.split('/').pop()}</span>
                </div>
                <div className="mt-1 flex items-center justify-between text-[10px] text-slate-500">
                  <span className="truncate max-w-[120px]">{item.path}</span>
                  <span className="font-mono text-emerald-400">+{item.additions}</span>
                </div>
              </button>
            );
          })}
        </div>

        {/* 右侧只读 Diff 预览 */}
        <div className="md:col-span-2 rounded-lg border border-slate-800 bg-slate-900/60 p-2.5 font-mono text-xs overflow-auto max-h-72">
          {activeChange ? (
            <div>
              <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800 text-[11px] text-slate-400">
                <span className="font-semibold text-slate-300">{activeChange.path}</span>
                <span className="text-[10px] uppercase text-indigo-400">
                  {activeChange.changeType}
                </span>
              </div>
              <pre className="whitespace-pre-wrap text-[11px] leading-relaxed text-slate-200">
                {activeChange.diffHunk}
              </pre>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-slate-500">
              暂无 Diff 变更
            </div>
          )}
        </div>
      </div>

      <div className="pt-2 border-t border-slate-800 text-[10px] text-slate-500">
        架构克制：本面板仅提供轻量代码核验与审查，严禁手动增删文件，不抢 IDE / Git 饭碗
      </div>
    </div>
  );
};
