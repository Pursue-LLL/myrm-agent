/**
 * [INPUT]
 * - react (POS: UI Framework)
 * - lucide-react (POS: Vector Icons)
 * - @/components/features/chat-window/memory-inspector/memoryInspectorTypes
 * - @/components/features/chat-window/memory-inspector/memoryInspectorEngine
 * - @/components/features/chat-window/memory-inspector/useMemoryInspectorStore
 *
 * [OUTPUT]
 * - VisualMemoryHealthCard (POS: White-box inspector card for memory readiness, deep diagnostic, and re-indexing)
 *
 * [POS]
 * Primary visual status card for Item 201 (P1): VisualMemoryReadinessAndVectorHealthInspectorSuite.
 * Renders vector store health attributes, end-to-end latency diagnostics (Embedding/Write/Cosine search),
 * and live re-indexing progress visualization to eliminate black-box retrieval uncertainty.
 */

import React from 'react';
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Zap,
  Gauge,
  RefreshCw,
  Database,
  Layers,
  Coins,
  ChevronDown,
  ChevronUp,
  X,
} from 'lucide-react';
import type {
  MemoryProviderStatus,
  LatencyRating,
} from './memoryInspectorTypes';
import { formatVectorStoreLabel } from './memoryInspectorEngine';
import { useMemoryInspectorStore } from './useMemoryInspectorStore';

export interface VisualMemoryHealthCardProps {
  readonly onDiagnosticComplete?: () => void;
  readonly onReindexStart?: () => void;
  readonly className?: string;
}

export const VisualMemoryHealthCard: React.FC<VisualMemoryHealthCardProps> = ({
  onDiagnosticComplete,
  onReindexStart,
  className = '',
}) => {
  const {
    health,
    lastDiagnostic,
    isDiagnosing,
    reindex,
    isDiagnosticPanelOpen,
    runDeepDiagnostic,
    startReindexing,
    cancelReindexing,
    toggleDiagnosticPanel,
  } = useMemoryInspectorStore();

  const handleRunDiagnostic = async () => {
    await runDeepDiagnostic();
    if (onDiagnosticComplete) {
      onDiagnosticComplete();
    }
  };

  const handleStartReindexing = () => {
    startReindexing();
    if (onReindexStart) {
      onReindexStart();
    }
  };

  const renderStatusBadge = (status: MemoryProviderStatus) => {
    switch (status) {
      case 'ready': {
        return (
          <span
            data-testid="badge-status-ready"
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-950/80 text-emerald-300 border border-emerald-800/80"
          >
            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
            <span>就绪 (Ready)</span>
          </span>
        );
      }
      case 'degraded': {
        return (
          <span
            data-testid="badge-status-degraded"
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-amber-950/80 text-amber-300 border border-amber-800/80"
          >
            <AlertTriangle className="w-3 h-3 text-amber-400" />
            <span>降级 (Degraded)</span>
          </span>
        );
      }
      default: {
        return (
          <span
            data-testid="badge-status-error"
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-rose-950/80 text-rose-300 border border-rose-800/80"
          >
            <AlertCircle className="w-3 h-3 text-rose-400" />
            <span>异常 (Error)</span>
          </span>
        );
      }
    }
  };

  const renderRatingBadge = (rating: LatencyRating) => {
    switch (rating) {
      case 'optimal': {
        return (
          <span
            data-testid="badge-rating-optimal"
            className="px-1.5 py-0.2 rounded text-[10px] font-medium bg-emerald-950 text-emerald-300 border border-emerald-800"
          >
            极速 (Optimal)
          </span>
        );
      }
      case 'acceptable': {
        return (
          <span
            data-testid="badge-rating-acceptable"
            className="px-1.5 py-0.2 rounded text-[10px] font-medium bg-cyan-950 text-cyan-300 border border-cyan-800"
          >
            良好 (Acceptable)
          </span>
        );
      }
      default: {
        return (
          <span
            data-testid="badge-rating-degraded"
            className="px-1.5 py-0.2 rounded text-[10px] font-medium bg-amber-950 text-amber-300 border border-amber-800"
          >
            缓慢 (Degraded)
          </span>
        );
      }
    }
  };

  return (
    <section
      data-testid="visual-memory-health-card"
      className={`flex flex-col gap-3 p-4 rounded-xl bg-slate-900/90 border border-slate-800 text-xs text-slate-200 shadow-md backdrop-blur-sm ${className}`}
    >
      {/* 头部：健康状态与控制按钮 */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Activity className="w-4 h-4 text-cyan-400 shrink-0" />
          <h3 className="font-semibold text-slate-100 text-sm truncate">
            记忆引擎白盒就绪看板
          </h3>
          {renderStatusBadge(health.status)}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            data-testid="btn-deep-diagnostic"
            aria-label="执行深度自检"
            disabled={isDiagnosing}
            onClick={handleRunDiagnostic}
            className="flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-medium bg-cyan-950/60 text-cyan-300 border border-cyan-800/60 hover:bg-cyan-900/60 disabled:opacity-50 transition-colors"
          >
            <Zap className={`w-3 h-3 ${isDiagnosing ? 'animate-bounce text-amber-400' : 'text-cyan-400'}`} />
            <span>{isDiagnosing ? '自检中...' : '深度自检'}</span>
          </button>

          <button
            type="button"
            data-testid="btn-force-reindex"
            aria-label="强制全量重索引"
            disabled={reindex.isReindexing}
            onClick={handleStartReindexing}
            className="flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-medium bg-slate-800/80 text-slate-300 border border-slate-700/60 hover:text-slate-100 hover:bg-slate-800 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`w-3 h-3 ${reindex.isReindexing ? 'animate-spin' : ''}`} />
            <span>重索引</span>
          </button>
        </div>
      </div>

      {/* 核心元数据网格 */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 border-t border-slate-800/60">
        <div className="p-2 rounded bg-slate-950/50 border border-slate-800/60">
          <span className="text-[10px] text-slate-500 block">Embedding 模型</span>
          <span
            data-testid="label-model-name"
            className="text-[11px] font-mono text-cyan-300 truncate block"
            title={health.modelName}
          >
            {health.modelName}
          </span>
        </div>

        <div className="p-2 rounded bg-slate-950/50 border border-slate-800/60">
          <span className="text-[10px] text-slate-500 block flex items-center gap-1">
            <Database className="w-2.5 h-2.5 text-slate-400" />
            向量引擎 / 维度
          </span>
          <span
            data-testid="label-vector-dims"
            className="text-[11px] font-mono text-slate-300 truncate block"
            title={formatVectorStoreLabel(health.vectorStore)}
          >
            {health.vectorDims} 维
          </span>
        </div>

        <div className="p-2 rounded bg-slate-950/50 border border-slate-800/60">
          <span className="text-[10px] text-slate-500 block flex items-center gap-1">
            <Layers className="w-2.5 h-2.5 text-slate-400" />
            已索引 Chunks
          </span>
          <span
            data-testid="label-chunks-count"
            className="text-[11px] font-mono text-emerald-400 font-medium block"
          >
            {health.indexedChunksCount.toLocaleString()}
          </span>
        </div>

        <div className="p-2 rounded bg-slate-950/50 border border-slate-800/60">
          <span className="text-[10px] text-slate-500 block">FTS 全文条目</span>
          <span
            data-testid="label-fts-count"
            className="text-[11px] font-mono text-purple-300 font-medium block"
          >
            {health.ftsEntriesCount.toLocaleString()}
          </span>
        </div>
      </div>

      {/* 重索引动态进度条 */}
      {reindex.isReindexing && (
        <div
          data-testid="reindex-progress-container"
          className="flex flex-col gap-1.5 p-3 rounded-lg bg-slate-950/80 border border-cyan-900/60 animate-fadeIn"
        >
          <div className="flex items-center justify-between text-[11px]">
            <span className="flex items-center gap-1.5 text-cyan-300 font-medium">
              <RefreshCw className="w-3 h-3 animate-spin text-cyan-400" />
              <span>向量重索引中：{reindex.progressPercent}%</span>
            </span>

            <div className="flex items-center gap-2 text-slate-400 font-mono text-[10px]">
              <span>
                {reindex.processedChunks} / {reindex.totalChunks} chunks
              </span>
              <span className="flex items-center gap-0.5 text-amber-400">
                <Coins className="w-2.5 h-2.5" />
                ~{reindex.estimatedTokensUsed.toLocaleString()} tokens
              </span>
              <button
                type="button"
                data-testid="btn-cancel-reindex"
                aria-label="取消重索引"
                onClick={cancelReindexing}
                className="p-0.5 rounded text-slate-500 hover:text-rose-400 transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
            <div
              data-testid="reindex-progress-bar"
              style={{ width: `${reindex.progressPercent}%` }}
              className="h-full bg-gradient-to-r from-cyan-500 to-emerald-400 transition-all duration-300 rounded-full"
            />
          </div>
        </div>
      )}

      {/* 深度自检细分指标折叠面板 */}
      {lastDiagnostic && (
        <div
          data-testid="diagnostic-results-panel"
          className="flex flex-col gap-2 p-3 rounded-lg bg-slate-950/60 border border-slate-800"
        >
          <button
            type="button"
            data-testid="btn-toggle-diagnostic"
            onClick={() => {
              toggleDiagnosticPanel();
            }}
            className="flex items-center justify-between w-full text-left cursor-pointer text-xs select-none hover:opacity-90 transition-opacity"
            aria-expanded={isDiagnosticPanelOpen}
            aria-label={isDiagnosticPanelOpen ? '折叠自检详情' : '展开自检详情'}
          >
            <div className="flex items-center gap-1.5 text-slate-300 font-medium">
              <Gauge className="w-3.5 h-3.5 text-cyan-400" />
              <span>端到端延迟诊断：{lastDiagnostic.totalMs} ms</span>
              {renderRatingBadge(lastDiagnostic.overallRating)}
            </div>

            <span className="text-slate-500 hover:text-slate-300">
              {isDiagnosticPanelOpen ? (
                <ChevronUp className="w-3.5 h-3.5" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5" />
              )}
            </span>
          </button>

          {isDiagnosticPanelOpen && (
            <div className="grid grid-cols-3 gap-2 pt-2 border-t border-slate-800/60 text-[10px] font-mono">
              <div className="flex flex-col p-1.5 rounded bg-slate-900 border border-slate-800">
                <span className="text-slate-500">Embedding API</span>
                <span data-testid="diag-latency-embedding" className="text-cyan-300 font-semibold">
                  {lastDiagnostic.embeddingMs} ms
                </span>
              </div>

              <div className="flex flex-col p-1.5 rounded bg-slate-900 border border-slate-800">
                <span className="text-slate-500">向量库写入</span>
                <span data-testid="diag-latency-write" className="text-emerald-300 font-semibold">
                  {lastDiagnostic.storageWriteMs} ms
                </span>
              </div>

              <div className="flex flex-col p-1.5 rounded bg-slate-900 border border-slate-800">
                <span className="text-slate-500">余弦检索</span>
                <span data-testid="diag-latency-cosine" className="text-purple-300 font-semibold">
                  {lastDiagnostic.cosineSearchMs} ms
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
};
