import React from 'react';
import {
  Undo2,
  Redo2,
  History,
  Check,
  Clock,
  GitCommit,
} from 'lucide-react';
import { useElementEditorStore } from './useElementEditorStore';

export const VisualVersionRollbackDeck: React.FC = () => {
  const {
    snapshots,
    currentSnapshotIndex,
    isHistoryOpen,
    undo,
    redo,
    rollbackToVersion,
    toggleHistoryDeck,
  } = useElementEditorStore();

  const currentSnapshot = snapshots[currentSnapshotIndex] || null;
  const canUndo = currentSnapshotIndex > 0;
  const canRedo = currentSnapshotIndex < snapshots.length - 1;

  const isMac =
    typeof navigator !== 'undefined' &&
    /Mac|iPod|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
  const undoShortcut = isMac ? '⌘Z' : 'Ctrl+Z';
  const redoShortcut = isMac ? '⇧⌘Z' : 'Ctrl+Y';

  return (
    <div
      data-testid="visual-version-rollback-deck"
      className="relative flex items-center gap-2 select-none"
    >
      {/* 撤销 / 悔棋按钮 */}
      <button
        type="button"
        onClick={() => undo()}
        disabled={!canUndo}
        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-900/90 hover:bg-slate-800 border border-slate-700/80 text-xs text-slate-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        title={`悔棋撤销 (${undoShortcut})`}
        aria-label="悔棋"
      >
        <Undo2 className="w-3.5 h-3.5 text-amber-400" />
        <span>悔棋</span>
        <span className="text-[10px] text-slate-500 font-mono hidden sm:inline">
          {undoShortcut}
        </span>
      </button>

      {/* 重做按钮 */}
      <button
        type="button"
        onClick={() => redo()}
        disabled={!canRedo}
        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-900/90 hover:bg-slate-800 border border-slate-700/80 text-xs text-slate-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        title={`重做 (${redoShortcut})`}
        aria-label="重做"
      >
        <Redo2 className="w-3.5 h-3.5 text-indigo-400" />
        <span>重做</span>
        <span className="text-[10px] text-slate-500 font-mono hidden sm:inline">
          {redoShortcut}
        </span>
      </button>

      {/* 当前版本指示与历史抽屉开关 */}
      <button
        type="button"
        onClick={toggleHistoryDeck}
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-mono transition-colors ${
          isHistoryOpen
            ? 'bg-indigo-600 text-white border-indigo-500 shadow-sm'
            : 'bg-slate-900/90 text-slate-300 border-slate-700 hover:border-slate-600'
        }`}
        title="查看版本历史时光机"
        aria-label="版本历史"
      >
        <History className="w-3.5 h-3.5 text-slate-400" />
        <span>v{currentSnapshot?.versionNumber || 1}</span>
      </button>

      {/* 版本历史时光机下拉抽屉 */}
      {isHistoryOpen && (
        <div
          data-testid="snapshot-history-popover"
          className="absolute top-10 right-0 z-40 w-72 bg-slate-950/95 backdrop-blur-md border border-slate-800 rounded-2xl p-3 shadow-2xl animate-in fade-in zoom-in-95 duration-100"
        >
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800 text-xs text-slate-400">
            <span className="font-semibold text-slate-200">版本快照时光机</span>
            <span className="text-[10px] font-mono">共 {snapshots.length} 个快照</span>
          </div>

          <div className="max-h-60 overflow-y-auto space-y-1.5 pr-0.5">
            {snapshots.map((snap, idx) => {
              const isCurrent = idx === currentSnapshotIndex;
              return (
                <button
                  key={snap.id}
                  type="button"
                  onClick={() => rollbackToVersion(snap.versionNumber)}
                  className={`w-full text-left p-2 rounded-xl border transition-all flex items-start justify-between ${
                    isCurrent
                      ? 'bg-indigo-950/60 border-indigo-500/50 text-indigo-200'
                      : 'bg-slate-900/40 border-slate-800/80 hover:bg-slate-900 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <div className="min-w-0 pr-2">
                    <div className="flex items-center gap-1.5 text-xs font-semibold">
                      <GitCommit className="w-3 h-3 text-indigo-400 shrink-0" />
                      <span className="font-mono">v{snap.versionNumber}</span>
                      {isCurrent && (
                        <span className="px-1.5 py-0.2 text-[9px] bg-indigo-500/20 text-indigo-300 rounded font-sans">
                          当前
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 text-[11px] truncate leading-tight">
                      {snap.description}
                    </p>
                    <div className="mt-1 flex items-center gap-1 text-[9px] text-slate-500 font-mono">
                      <Clock className="w-2.5 h-2.5" />
                      <span>{snap.timestamp}</span>
                      <span className="ml-1 text-emerald-400">
                        +{snap.diffStats.addedLines}
                      </span>
                      {snap.diffStats.removedLines > 0 && (
                        <span className="text-rose-400">
                          -{snap.diffStats.removedLines}
                        </span>
                      )}
                    </div>
                  </div>

                  {isCurrent && (
                    <Check className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
