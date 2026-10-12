/**
 * [INPUT]
 * @/services/memory::(fetchQuadrupleRetrievalStats, executeQuadrupleSearch, QuadrupleRetrievalStatsDTO, QuadrupleSearchResponse)
 * ./quadrupleRetrievalFallbacks::(FALLBACK_RETRIEVAL_STATS, FALLBACK_SEARCH_RESPONSE)
 * ./QuadrupleRetrievalHudBar::QuadrupleRetrievalHudBar
 * ./TaskGoalParserConsoleView::TaskGoalParserConsoleView
 * ./QuadrupleRecallMatrixView::QuadrupleRecallMatrixView
 * ./ReasonerHarmonizerCard::ReasonerHarmonizerCard
 * lucide-react::(Search, Sparkles, Filter, AlertCircle, Compass, ListOrdered)
 *
 * [OUTPUT]
 * Component: QuadrupleRetrievalStudioCard
 *
 * [POS]
 * Studio workbench card for Item 127 Goal-Driven Quadruple Retrieval & Reasoner Suite.
 * Interactive query decomposition, 4-way parallel recall matrix, and semantic reasoner reranking.
 * A11y compliant: Semantic forms, native labels, visible focus rings, zero div role="button".
 * Strict typing: Zero `any`. Single file < 350 lines.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Search, Sparkles, Filter, AlertCircle, Compass, ListOrdered } from 'lucide-react';
import {
  fetchQuadrupleRetrievalStats,
  executeQuadrupleSearch,
  type QuadrupleRetrievalStatsDTO,
  type QuadrupleSearchResponse,
} from '@/services/memory';
import {
  FALLBACK_RETRIEVAL_STATS,
  FALLBACK_SEARCH_RESPONSE,
} from './quadrupleRetrievalFallbacks';
import { QuadrupleRetrievalHudBar } from './QuadrupleRetrievalHudBar';
import { TaskGoalParserConsoleView } from './TaskGoalParserConsoleView';
import { QuadrupleRecallMatrixView } from './QuadrupleRecallMatrixView';
import { ReasonerHarmonizerCard } from './ReasonerHarmonizerCard';

const PRESET_QUERIES = [
  {
    label: '架构红线与类型约束',
    query: '帮我查一下项目关于单文件行数限制和 TypeScript any 类型的架构红线要求',
  },
  {
    label: '前端门禁与a11y',
    query: '查询前端工程规范中关于 check-a11y-ratchet 门禁与语义标签的规则',
  },
  {
    label: '四路并行检索架构',
    query: 'QuadrupleParallelRetriever 四路并行召回协议与多通道融合机制',
  },
  {
    label: '过时方案衰减惩罚',
    query: '检索关于集中式全量检索 router proxy 与废弃网关的记忆',
  },
];

export const QuadrupleRetrievalStudioCard: React.FC = () => {
  const [stats, setStats] = useState<QuadrupleRetrievalStatsDTO>(FALLBACK_RETRIEVAL_STATS);
  const [searchResponse, setSearchResponse] = useState<QuadrupleSearchResponse>(FALLBACK_SEARCH_RESPONSE);
  const [queryInput, setQueryInput] = useState<string>(FALLBACK_SEARCH_RESPONSE.query);
  const [topK, setTopK] = useState<number>(4);
  const [isStatsLoading, setIsStatsLoading] = useState<boolean>(false);
  const [isSearching, setIsSearching] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadStats = useCallback(async () => {
    setIsStatsLoading(true);
    try {
      const data = await fetchQuadrupleRetrievalStats();
      setStats(data);
    } catch {
      setStats(FALLBACK_RETRIEVAL_STATS);
    } finally {
      setIsStatsLoading(false);
    }
  }, []);

  const handleExecuteSearch = useCallback(async (queryToRun: string, topKLimit: number) => {
    const trimmed = queryToRun.trim();
    if (!trimmed) return;

    setIsSearching(true);
    setErrorMessage(null);
    try {
      const res = await executeQuadrupleSearch({
        query: trimmed,
        top_k: topKLimit,
      });
      setSearchResponse(res);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : '四路并行检索执行失败，展示兜底数据');
      setSearchResponse(FALLBACK_SEARCH_RESPONSE);
    } finally {
      setIsSearching(false);
    }
  }, []);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void handleExecuteSearch(queryInput, topK);
  };

  const handleSelectPreset = (presetQuery: string) => {
    setQueryInput(presetQuery);
    void handleExecuteSearch(presetQuery, topK);
  };

  return (
    <section
      aria-label="目标驱动四路并行检索与推理重排工作台"
      className="p-5 rounded-xl border border-border/80 bg-card/60 backdrop-blur-sm space-y-4 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <Compass className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-foreground">
              四路并行检索与推理重排工作台
            </h2>
            <p className="text-xs text-muted-foreground">
              MemOS 混合检索架构 · 前置 TaskGoalParser 消除自然语言噪音 · Reasoner 语义推理重排
            </p>
          </div>
        </div>

        <span className="px-2.5 py-1 rounded-md text-xs font-mono font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
          Item 127 · P1 Production Ready
        </span>
      </div>

      <QuadrupleRetrievalHudBar
        stats={stats}
        isLoading={isStatsLoading}
        onRefresh={() => void loadStats()}
      />

      <form onSubmit={handleSubmit} className="p-4 rounded-lg border border-border/70 bg-card/50 space-y-3">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
          <div className="relative flex-1">
            <label htmlFor="quadruple-search-input" className="sr-only">
              输入自然语言检索目标
            </label>
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" aria-hidden="true" />
            <input
              id="quadruple-search-input"
              type="text"
              value={queryInput}
              onChange={(e) => setQueryInput(e.target.value)}
              placeholder="输入自然语言查询（如：项目单文件行数限制和 any 类型红线）..."
              className="w-full pl-9 pr-3 py-2 text-xs rounded-md border border-border/80 bg-background text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary transition-all"
            />
          </div>

          <div className="flex items-center gap-2">
            <label htmlFor="quadruple-top-k-select" className="text-xs font-medium text-muted-foreground whitespace-nowrap">
              Top-K:
            </label>
            <select
              id="quadruple-top-k-select"
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="py-1.5 px-2.5 text-xs rounded-md border border-border/80 bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value={2}>2 条</option>
              <option value={4}>4 条</option>
              <option value={6}>6 条</option>
              <option value={10}>10 条</option>
            </select>

            <button
              type="submit"
              disabled={isSearching || !queryInput.trim()}
              aria-label="执行四路并行检索"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md text-xs font-semibold bg-primary text-primary-foreground hover:bg-primary/90 transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50 whitespace-nowrap"
            >
              <Sparkles className={`w-3.5 h-3.5 ${isSearching ? 'animate-spin' : ''}`} aria-hidden="true" />
              {isSearching ? '四路召回中...' : '开始检索'}
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-border/40 text-xs">
          <span className="flex items-center gap-1 text-muted-foreground font-medium">
            <Filter className="w-3 h-3" aria-hidden="true" /> 快速样本:
          </span>
          {PRESET_QUERIES.map((preset) => (
            <button
              key={preset.label}
              type="button"
              onClick={() => handleSelectPreset(preset.query)}
              aria-label={`载入预设查询: ${preset.label}`}
              className="px-2.5 py-1 rounded-md text-[11px] font-medium border border-border/70 bg-muted/30 hover:bg-muted/70 text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {preset.label}
            </button>
          ))}
        </div>
      </form>

      {errorMessage && (
        <output
          aria-live="polite"
          className="flex items-center gap-2 p-3 rounded-lg border border-amber-500/30 bg-amber-500/10 text-xs text-amber-700 dark:text-amber-400 font-medium block"
        >
          <AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />
          <span>{errorMessage}</span>
        </output>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <TaskGoalParserConsoleView goal={searchResponse.parsed_goal} />
        <QuadrupleRecallMatrixView
          channelHits={searchResponse.channel_hits_count}
          fusedCandidatesCount={searchResponse.fused_candidates_count}
          channelWeights={stats.channel_weights}
        />
      </div>

      <section
        aria-label="推理重排结果列表"
        className="p-4 rounded-lg border border-border/80 bg-card/40 space-y-3"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-2.5">
          <div className="flex items-center gap-2">
            <div className="p-1 rounded bg-primary/10 text-primary">
              <ListOrdered className="w-3.5 h-3.5" aria-hidden="true" />
            </div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Reasoner 语义推理重排结果 (Top-{searchResponse.final_hits.length})
            </h3>
          </div>

          <span className="text-xs font-mono text-muted-foreground">
            端到端执行延迟: {searchResponse.latency_ms.toFixed(1)} ms
          </span>
        </div>

        {searchResponse.final_hits.length === 0 ? (
          <div className="p-6 text-center text-xs text-muted-foreground">
            未召回到符合条件的记忆条目，请调整查询或放宽约束
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-2.5">
            {searchResponse.final_hits.map((hit) => (
              <ReasonerHarmonizerCard key={hit.memory_id} hit={hit} />
            ))}
          </div>
        )}
      </section>
    </section>
  );
};
