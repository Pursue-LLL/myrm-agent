/**
 * [INPUT]
 * @/services/memory::SqliteVecSearchRequest
 * ./sqliteVecFallbacks::SAMPLE_QUERY_VECTORS
 * Lucide icons (Search, Sparkles, Sliders, Clock)
 *
 * [OUTPUT]
 * Component: SqliteVecQueryConsoleView
 *
 * [POS]
 * Dense vector retrieval interactive console for Item 130 SqliteVec Studio.
 * Strictly typed, zero any, a11y compliant with visible focus rings and valid labels. Single file < 250 lines.
 */

'use client';

import React from 'react';
import { Clock, Search, Sliders, Sparkles } from 'lucide-react';
import { SAMPLE_QUERY_VECTORS } from './sqliteVecFallbacks';

interface SqliteVecQueryConsoleViewProps {
  selectedVectorIndex: number;
  onSelectVectorIndex: (index: number) => void;
  applyDecay: boolean;
  onToggleApplyDecay: (enabled: boolean) => void;
  scoreThreshold: number;
  onChangeScoreThreshold: (threshold: number) => void;
  onSearch: () => void;
  isSearching: boolean;
}

export const SqliteVecQueryConsoleView: React.FC<SqliteVecQueryConsoleViewProps> = ({
  selectedVectorIndex,
  onSelectVectorIndex,
  applyDecay,
  onToggleApplyDecay,
  scoreThreshold,
  onChangeScoreThreshold,
  onSearch,
  isSearching,
}) => {
  const currentSample = SAMPLE_QUERY_VECTORS[selectedVectorIndex] || SAMPLE_QUERY_VECTORS[0];

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isSearching) {
      onSearch();
    }
  };

  return (
    <section
      aria-label="稠密向量检索与时间半衰期衰减配置控制台"
      className="space-y-4 rounded-xl border border-border/80 bg-card/60 p-4 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
          <h3 className="text-sm font-semibold text-foreground">
            稠密向量近邻检索控制台 (Dense Vector Retrieval Console)
          </h3>
        </div>
        <span className="text-xs text-muted-foreground">
          基于单文件 SQLite 原生扩展或进程内 BLOB 双轨执行
        </span>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Preset Query Vectors Selection */}
        <div className="space-y-2">
          <span className="text-xs font-medium text-foreground">
            选择测试查询向量样本 (8-Dimension Normalized Sample):
          </span>
          <div className="flex flex-wrap gap-2">
            {SAMPLE_QUERY_VECTORS.map((sample, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => onSelectVectorIndex(idx)}
                disabled={isSearching}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition focus:outline-none focus:ring-2 focus:ring-primary ${
                  selectedVectorIndex === idx
                    ? 'border-primary bg-primary/10 text-primary shadow-xs'
                    : 'border-border bg-background text-foreground hover:bg-muted'
                } disabled:opacity-50`}
              >
                {sample.label}
              </button>
            ))}
          </div>
          <div className="rounded-md border border-border/40 bg-muted/40 p-2 font-mono text-[11px] text-muted-foreground">
            Vector: [{currentSample.vector.map((v) => v.toFixed(2)).join(', ')}]
          </div>
        </div>

        {/* Search Parameters & Controls */}
        <div className="grid grid-cols-1 gap-4 rounded-lg border border-border/60 bg-muted/20 p-3 sm:grid-cols-2">
          {/* Temporal decay toggle */}
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-primary/80" aria-hidden="true" />
              <div>
                <label
                  htmlFor="sqlite-vec-apply-decay-checkbox"
                  className="text-xs font-medium text-foreground"
                >
                  艾宾浩斯时间半衰期衰减
                </label>
                <p className="text-[11px] text-muted-foreground">
                  指数衰减旧记忆得分，保护持久规范
                </p>
              </div>
            </div>
            <input
              id="sqlite-vec-apply-decay-checkbox"
              type="checkbox"
              checked={applyDecay}
              onChange={(e) => onToggleApplyDecay(e.target.checked)}
              disabled={isSearching}
              className="h-4 w-4 rounded border-input text-primary focus:ring-2 focus:ring-primary"
            />
          </div>

          {/* Score threshold control */}
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Sliders className="h-4 w-4 text-primary/80" aria-hidden="true" />
              <div>
                <label
                  htmlFor="sqlite-vec-score-threshold-input"
                  className="text-xs font-medium text-foreground"
                >
                  相似度下限阈值
                </label>
                <p className="text-[11px] text-muted-foreground">
                  过滤低于此得分的候选文档
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <input
                id="sqlite-vec-score-threshold-input"
                type="number"
                min="0"
                max="1"
                step="0.05"
                value={scoreThreshold}
                onChange={(e) => onChangeScoreThreshold(parseFloat(e.target.value) || 0)}
                disabled={isSearching}
                className="w-16 rounded border border-input bg-background px-2 py-1 text-center font-mono text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>
        </div>

        {/* Submit Button */}
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={isSearching}
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-medium text-primary-foreground shadow transition hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 disabled:pointer-events-none disabled:opacity-50"
          >
            <Search className="h-4 w-4" aria-hidden="true" />
            <span>{isSearching ? '检索向量中...' : '执行稠密向量检索'}</span>
          </button>
        </div>
      </form>
    </section>
  );
};
