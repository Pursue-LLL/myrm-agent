/**
 * [INPUT]
 * lucide-react::FileText, Split, Layers, Percent, RefreshCw (POS: UI icons)
 *
 * [OUTPUT]
 * Component: MarkdownChunkerHudBar
 *
 * [POS]
 * Real-time HUD summary bar for Markdown Sliding Window Chunker Suite.
 * Displays source document path, total generated chunks, overlap budget,
 * and token savings telemetry. Accessible and strictly typed. Single file < 200 lines.
 */

import React from 'react';
import { FileText, Split, Layers, Percent, RefreshCw } from 'lucide-react';

interface MarkdownChunkerHudBarProps {
  sourcePath: string;
  totalChunks: number;
  overlapTokens: number;
  tokenSavingsPct: number;
  status: string;
  isLoading: boolean;
  onRefresh: () => void;
}

export const MarkdownChunkerHudBar: React.FC<MarkdownChunkerHudBarProps> = ({
  sourcePath,
  totalChunks,
  overlapTokens,
  tokenSavingsPct,
  status,
  isLoading,
  onRefresh,
}) => {
  const isPartiallyOrFullyUpdated =
    status === 'partially_updated' || status === 'unchanged';

  return (
    <header className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl bg-card border border-border shadow-sm">
      <div className="flex items-center gap-3">
        <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-primary/10 text-primary">
          <Split className="w-5 h-5" aria-hidden="true" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-foreground text-sm tracking-tight">
              Markdown 滑动窗口切片与增量索引
            </h3>
            <span
              className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                isPartiallyOrFullyUpdated
                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                  : 'bg-primary/10 text-primary border border-primary/20'
              }`}
            >
              {status === 'partially_updated'
                ? '增量命中'
                : status === 'unchanged'
                  ? '全部复用'
                  : '就绪'}
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1.5">
            <FileText className="w-3.5 h-3.5 text-muted-foreground" aria-hidden="true" />
            <span>目标源文档：</span>
            <span className="font-mono text-foreground font-medium">{sourcePath || '未选择'}</span>
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-6 text-xs text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <Layers className="w-3.5 h-3.5 text-primary" aria-hidden="true" />
          <span>切片总量:</span>
          <span className="font-mono font-medium text-foreground">
            {totalChunks} 块
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <Split className="w-3.5 h-3.5 text-primary" aria-hidden="true" />
          <span>相邻重叠:</span>
          <span className="font-mono font-medium text-foreground">
            {overlapTokens} tokens
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <Percent className="w-3.5 h-3.5 text-emerald-500" aria-hidden="true" />
          <span>Token 节省率:</span>
          <span className="font-mono font-semibold text-emerald-600 dark:text-emerald-400">
            {tokenSavingsPct.toFixed(1)}%
          </span>
        </div>

        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          aria-label="刷新切片状态"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-background hover:bg-muted text-foreground transition-colors disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <RefreshCw
            className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`}
            aria-hidden="true"
          />
          <span>重切</span>
        </button>
      </div>
    </header>
  );
};
