/**
 * Interactive Multi-Factor Adaptive RRF Rank Visualizer and Parameter Tuner.
 */

import React from 'react';
import { Sliders, Clock, Sparkles, Check, Database, Cpu } from 'lucide-react';
import type { AdaptiveRrfConfigDTO, HybridSearchResultDTO } from '@/services/memory/hybridSearch';

interface AdaptiveRrfRankVisualizerViewProps {
  config: AdaptiveRrfConfigDTO;
  onChangeConfig: (newConfig: AdaptiveRrfConfigDTO) => void;
  results: HybridSearchResultDTO[];
  onApplyRerank: () => void;
  isLoading: boolean;
}

export const AdaptiveRrfRankVisualizerView: React.FC<AdaptiveRrfRankVisualizerViewProps> = ({
  config,
  onChangeConfig,
  results,
  onApplyRerank,
  isLoading,
}) => {
  const getChannelBadge = (channel: string) => {
    switch (channel) {
      case 'rrf_hybrid':
        return (
          <span className="inline-flex items-center gap-1 rounded bg-indigo-500/10 px-1.5 py-0.5 text-[11px] font-semibold text-indigo-600 dark:text-indigo-400">
            <Sparkles className="h-3 w-3" aria-hidden="true" />
            RRF 融合
          </span>
        );
      case 'vector':
        return (
          <span className="inline-flex items-center gap-1 rounded bg-purple-500/10 px-1.5 py-0.5 text-[11px] font-medium text-purple-600 dark:text-purple-400">
            <Cpu className="h-3 w-3" aria-hidden="true" />
            稠密向量
          </span>
        );
      case 'fts_degraded':
        return (
          <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-1.5 py-0.5 text-[11px] font-medium text-amber-600 dark:text-amber-400">
            <Database className="h-3 w-3" aria-hidden="true" />
            FTS 降级
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded bg-blue-500/10 px-1.5 py-0.5 text-[11px] font-medium text-blue-600 dark:text-blue-400">
            <Database className="h-3 w-3" aria-hidden="true" />
            SQLite FTS
          </span>
        );
    }
  };

  return (
    <section className="space-y-6">
      {/* Parameter Control Panel */}
      <div className="rounded-xl border border-border/70 bg-card p-5 shadow-sm">
        <div className="flex items-center justify-between border-b border-border/50 pb-3">
          <div className="flex items-center gap-2">
            <Sliders className="h-4 w-4 text-primary" aria-hidden="true" />
            <h3 className="text-sm font-semibold text-foreground">自适应多因子 RRF 融合重排参数调控</h3>
          </div>
          <button
            type="button"
            onClick={onApplyRerank}
            disabled={isLoading}
            aria-label="应用重排参数重新检索"
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground shadow hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50"
          >
            <Check className="h-3.5 w-3.5" aria-hidden="true" />
            应用重排参数
          </button>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
          {/* RRF K */}
          <div>
            <label htmlFor="rrf-k-input" className="block text-xs font-medium text-muted-foreground">
              RRF 平滑常数 (k: {config.rrf_k})
            </label>
            <input
              id="rrf-k-input"
              type="range"
              min={1}
              max={120}
              step={1}
              value={config.rrf_k}
              onChange={(e) => onChangeConfig({ ...config, rrf_k: Number(e.target.value) })}
              className="mt-2 w-full accent-primary focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <span className="text-[11px] text-muted-foreground">调节低排名候选的平滑衰减梯度 (标准值: 60)</span>
          </div>

          {/* FTS Weight */}
          <div>
            <label htmlFor="fts-weight-input" className="block text-xs font-medium text-muted-foreground">
              FTS5 BM25 权重比 (x{config.fts_weight.toFixed(1)})
            </label>
            <input
              id="fts-weight-input"
              type="range"
              min={0.1}
              max={3.0}
              step={0.1}
              value={config.fts_weight}
              onChange={(e) => onChangeConfig({ ...config, fts_weight: Number(e.target.value) })}
              className="mt-2 w-full accent-primary focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <span className="text-[11px] text-muted-foreground">词法精确匹配渠道在融合公式中的相对权重</span>
          </div>

          {/* Vector Weight */}
          <div>
            <label htmlFor="vector-weight-input" className="block text-xs font-medium text-muted-foreground">
              稠密向量语义权重比 (x{config.vector_weight.toFixed(1)})
            </label>
            <input
              id="vector-weight-input"
              type="range"
              min={0.1}
              max={3.0}
              step={0.1}
              value={config.vector_weight}
              onChange={(e) => onChangeConfig({ ...config, vector_weight: Number(e.target.value) })}
              className="mt-2 w-full accent-primary focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <span className="text-[11px] text-muted-foreground">语义嵌入通道在融合公式中的相对权重</span>
          </div>

          {/* Importance Weight */}
          <div>
            <label htmlFor="importance-weight-input" className="block text-xs font-medium text-muted-foreground">
              认知重要性加权系数 ({config.importance_weight.toFixed(2)})
            </label>
            <input
              id="importance-weight-input"
              type="range"
              min={0.0}
              max={1.0}
              step={0.05}
              value={config.importance_weight}
              onChange={(e) => onChangeConfig({ ...config, importance_weight: Number(e.target.value) })}
              className="mt-2 w-full accent-primary focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <span className="text-[11px] text-muted-foreground">核心长期记忆单元的提权倍率 (0.0 为禁用加权)</span>
          </div>

          {/* Recency Decay Toggle */}
          <div className="flex flex-col justify-center">
            <div className="flex items-center gap-2">
              <input
                id="recency-decay-checkbox"
                type="checkbox"
                checked={config.apply_recency_decay}
                onChange={(e) => onChangeConfig({ ...config, apply_recency_decay: e.target.checked })}
                className="h-4 w-4 rounded border-border accent-primary focus:ring-2 focus:ring-primary"
              />
              <label htmlFor="recency-decay-checkbox" className="text-xs font-medium text-foreground">
                启用艾宾浩斯时间半衰期衰减
              </label>
            </div>
            <span className="mt-1 text-[11px] text-muted-foreground">
              半衰期 24 小时：新鲜近效记忆保持满分，历史冷记忆平滑衰减
            </span>
          </div>
        </div>
      </div>

      {/* Reranked Candidate List */}
      <div className="rounded-xl border border-border/70 bg-card p-5 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
            <h3 className="text-sm font-semibold text-foreground">自适应重排命中结果序列 ({results.length})</h3>
          </div>
          <span className="text-xs text-muted-foreground">
            综合得分公式：RRF(k) × 时间衰减 × 重要性倍率
          </span>
        </div>

        <div className="divide-y divide-border/40">
          {results.map((hit) => {
            const scorePercent = Math.min(100, Math.max(0, Math.round(hit.score * 100)));
            return (
              <article key={hit.item_id} className="py-3.5 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                        {hit.rank}
                      </span>
                      <h4 className="text-sm font-semibold text-foreground">{hit.title || hit.item_id}</h4>
                      {getChannelBadge(hit.source_channel)}
                    </div>
                    <p className="line-clamp-2 text-xs text-muted-foreground">{hit.content}</p>
                  </div>

                  <div className="min-w-[120px] text-right">
                    <div className="text-xs font-bold text-foreground">
                      {(hit.score * 100).toFixed(1)}%
                    </div>
                    <div className="mt-1">
                      <progress
                        value={scorePercent}
                        max={100}
                        aria-label={`记忆 ${hit.item_id} 综合重排置信度得分`}
                        className="h-1.5 w-full overflow-hidden rounded-full [&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-value]:bg-primary [&::-moz-progress-bar]:bg-primary"
                      />
                    </div>
                  </div>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-4 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" aria-hidden="true" />
                    时效衰减系数：{(hit.recency_factor * 100).toFixed(1)}%
                  </span>
                  <span>重要性评分：{hit.importance.toFixed(2)}</span>
                  {hit.matched_terms.length > 0 && (
                    <span>匹配特征：{hit.matched_terms.join('、')}</span>
                  )}
                  {hit.is_degraded && (
                    <span className="font-medium text-amber-600 dark:text-amber-400">
                      降级原因：{hit.degradation_reason || '向量服务超时'}
                    </span>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
};
