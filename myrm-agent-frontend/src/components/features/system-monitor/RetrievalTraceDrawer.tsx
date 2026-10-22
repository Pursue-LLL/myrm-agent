'use client';

/**
 * [INPUT]
 * - ./types::VisitedPathTrace, RetrievalSimulateRequest (POS: 决策轨迹契约)
 * - ./RetrievalDecisionTreeView::RetrievalDecisionTreeView (POS: 树状渲染视图)
 * - lucide-react::GitBranch, Sliders, Play, X, Clock, Layers, Scissors, CheckCircle2 (POS: 视觉指示图标)
 *
 * [OUTPUT]
 * - RetrievalTraceDrawer: 上下文检索决策树与 OpenViking 实验场排障抽屉视窗
 *
 * [POS]
 * src/components/features/system-monitor/RetrievalTraceDrawer.tsx — 检索决策树控制台与实验场抽屉。
 */

import React, { useState } from 'react';
import {
  GitBranch,
  Sliders,
  Play,
  X,
  Clock,
  Layers,
  Scissors,
  CheckCircle2,
} from 'lucide-react';
import type { VisitedPathTrace } from './types';
import { RetrievalDecisionTreeView } from './RetrievalDecisionTreeView';

interface RetrievalTraceDrawerProps {
  trace: VisitedPathTrace;
  isOpen: boolean;
  onClose: () => void;
  onSimulate?: (threshold: number, topK: number) => Promise<void>;
  isSimulating?: boolean;
  className?: string;
}

export const RetrievalTraceDrawer: React.FC<RetrievalTraceDrawerProps> = ({
  trace,
  isOpen,
  onClose,
  onSimulate,
  isSimulating = false,
  className = '',
}) => {
  const [threshold, setThreshold] = useState<number>(0.75);
  const [topK, setTopK] = useState<number>(3);

  if (!isOpen) {
    return null;
  }

  const handleSimulate = async () => {
    if (!onSimulate) return;
    await onSimulate(threshold, topK);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="retrieval-drawer-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm"
    >
      <div
        className={`w-full max-w-3xl bg-card border border-border rounded-xl shadow-2xl flex flex-col max-h-[90vh] overflow-hidden ${className}`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-muted/40">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <GitBranch className="w-5 h-5" />
            </div>
            <div>
              <h2 id="retrieval-drawer-title" className="text-base font-semibold text-foreground">
                上下文检索决策树与剪枝留痕 (Retrieval Trace)
              </h2>
              <p className="text-xs text-muted-foreground">
                Trace: {trace.trace_id} · 查询: “{trace.query}”
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="关闭抽屉"
            className="p-1.5 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 顶部统计卡片 */}
        <div className="px-6 py-3 border-b border-border bg-muted/20 grid grid-cols-4 gap-3 text-xs">
          <div className="flex items-center gap-2 p-2 rounded-lg bg-background border border-border">
            <Clock className="w-4 h-4 text-primary shrink-0" />
            <div>
              <div className="text-[10px] text-muted-foreground">检索耗时</div>
              <div className="font-semibold font-mono">{trace.duration_ms.toFixed(1)} ms</div>
            </div>
          </div>

          <div className="flex items-center gap-2 p-2 rounded-lg bg-background border border-border">
            <Layers className="w-4 h-4 text-blue-500 shrink-0" />
            <div>
              <div className="text-[10px] text-muted-foreground">遍历节点</div>
              <div className="font-semibold font-mono">{trace.total_nodes_visited} 个</div>
            </div>
          </div>

          <div className="flex items-center gap-2 p-2 rounded-lg bg-background border border-border">
            <Scissors className="w-4 h-4 text-destructive shrink-0" />
            <div>
              <div className="text-[10px] text-muted-foreground">剪枝拦截</div>
              <div className="font-semibold font-mono text-destructive">{trace.pruned_nodes_count} 个</div>
            </div>
          </div>

          <div className="flex items-center gap-2 p-2 rounded-lg bg-background border border-border">
            <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
            <div>
              <div className="text-[10px] text-muted-foreground">最终命中装配</div>
              <div className="font-semibold font-mono text-emerald-600 dark:text-emerald-400">{trace.hits_count} 个</div>
            </div>
          </div>
        </div>

        {/* 主体决策树视图 */}
        <div className="p-6 overflow-y-auto flex-1">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
            分层下钻与剪枝判定树 (Hierarchical Traversal Tree)
          </h3>
          <RetrievalDecisionTreeView nodes={trace.root_nodes} />
        </div>

        {/* 底部 OpenViking 风格实验场模拟控制器 */}
        <div className="px-6 py-4 border-t border-border bg-muted/40">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-4 w-full sm:w-auto text-xs">
              <div className="flex items-center gap-1.5 text-muted-foreground shrink-0">
                <Sliders className="w-3.5 h-3.5" />
                <span>实验场参数:</span>
              </div>

              {/* 阈值滑块 */}
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-muted-foreground">剪枝阈值:</span>
                <input
                  type="range"
                  min="0.5"
                  max="0.95"
                  step="0.05"
                  value={threshold}
                  onChange={(e) => setThreshold(parseFloat(e.target.value))}
                  className="w-20 accent-primary cursor-pointer"
                  aria-label="剪枝阈值调节"
                />
                <span className="font-mono text-xs text-foreground font-medium w-8">
                  {threshold.toFixed(2)}
                </span>
              </div>

              {/* Top-K 滑块 */}
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-muted-foreground">Top-K:</span>
                <input
                  type="range"
                  min="1"
                  max="8"
                  step="1"
                  value={topK}
                  onChange={(e) => setTopK(parseInt(e.target.value, 10))}
                  className="w-16 accent-primary cursor-pointer"
                  aria-label="Top-K 数量调节"
                />
                <span className="font-mono text-xs text-foreground font-medium w-4">
                  {topK}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs font-medium rounded-lg hover:bg-accent text-foreground transition-colors"
              >
                关闭
              </button>
              <button
                type="button"
                disabled={!onSimulate || isSimulating}
                onClick={handleSimulate}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors shadow-sm"
              >
                <Play className={`w-3.5 h-3.5 ${isSimulating ? 'animate-spin' : ''}`} />
                <span>{isSimulating ? '模拟计算中...' : '实验场模拟重算'}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
