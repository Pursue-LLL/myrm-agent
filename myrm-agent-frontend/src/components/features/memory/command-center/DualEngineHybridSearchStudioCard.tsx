/**
 * Studio card for Dual-Engine Hybrid Search and Graceful Fallback Suite (Item 133).
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Search, Sliders, Shield, Database, Sparkles, AlertCircle } from 'lucide-react';
import {
  hybridSearchService,
  type AdaptiveRrfConfigDTO,
  type HybridEngineStatsDTO,
  type HybridSearchResultDTO,
} from '@/services/memory/hybridSearch';
import {
  INITIAL_ADAPTIVE_RRF_CONFIG,
  INITIAL_HYBRID_STATS,
  INITIAL_SEARCH_RESULTS,
} from './hybridSearchFallbacks';
import { HybridSearchHudBar } from './HybridSearchHudBar';
import { AdaptiveRrfRankVisualizerView } from './AdaptiveRrfRankVisualizerView';
import { CircuitBreakerFallbackConsoleView } from './CircuitBreakerFallbackConsoleView';

type ActiveTab = 'search' | 'rrf' | 'breaker';

export const DualEngineHybridSearchStudioCard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>('search');
  const [searchQuery, setSearchQuery] = useState('SQLite FTS5 架构与向量检索');
  const [enableVector, setEnableVector] = useState(true);
  const [stats, setStats] = useState<HybridEngineStatsDTO>(INITIAL_HYBRID_STATS);
  const [results, setResults] = useState<HybridSearchResultDTO[]>(INITIAL_SEARCH_RESULTS);
  const [rrfConfig, setRrfConfig] = useState<AdaptiveRrfConfigDTO>(INITIAL_ADAPTIVE_RRF_CONFIG);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadStats = useCallback(async () => {
    try {
      const data = await hybridSearchService.getStats();
      setStats(data);
    } catch {
      // Graceful fallback to initial stats
    }
  }, []);

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) return;
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await hybridSearchService.search({
        query: searchQuery.trim(),
        limit: 10,
        enable_vector: enableVector,
        adaptive_rrf: rrfConfig,
      });
      setResults(res.results);
      await loadStats();
    } catch {
      setErrorMessage('无法连接后端服务，已加载预置双引擎检索离线结果');
      setResults(INITIAL_SEARCH_RESULTS);
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery, enableVector, rrfConfig, loadStats]);

  const handleTripBreaker = useCallback(async () => {
    setIsLoading(true);
    try {
      await hybridSearchService.tripCircuitBreaker('Manual UI simulation test');
      await loadStats();
      await handleSearch();
    } catch {
      setStats((prev) => ({
        ...prev,
        active_mode: 'degraded_fallback',
        circuit_breaker: {
          ...prev.circuit_breaker,
          state: 'open',
          tripped_count: prev.circuit_breaker.tripped_count + 1,
        },
      }));
    } finally {
      setIsLoading(false);
    }
  }, [loadStats, handleSearch]);

  const handleResetBreaker = useCallback(async () => {
    setIsLoading(true);
    try {
      await hybridSearchService.resetCircuitBreaker();
      await loadStats();
      await handleSearch();
    } catch {
      setStats((prev) => ({
        ...prev,
        active_mode: 'hybrid_rrf',
        circuit_breaker: {
          ...prev.circuit_breaker,
          state: 'closed',
        },
      }));
    } finally {
      setIsLoading(false);
    }
  }, [loadStats, handleSearch]);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  return (
    <div className="space-y-6">
      {/* HUD Telemetry Banner */}
      <HybridSearchHudBar
        stats={stats}
        isLoading={isLoading}
        onRefresh={() => void loadStats()}
        onTripBreaker={() => void handleTripBreaker()}
        onResetBreaker={() => void handleResetBreaker()}
      />

      {/* Navigation Tabs */}
      <div className="flex border-b border-border/60">
        <button
          type="button"
          onClick={() => setActiveTab('search')}
          className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
            activeTab === 'search'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <Search className="h-4 w-4" aria-hidden="true" />
          双引擎实时检索
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('rrf')}
          className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
            activeTab === 'rrf'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <Sliders className="h-4 w-4" aria-hidden="true" />
          自适应 RRF 融合调优
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('breaker')}
          className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
            activeTab === 'breaker'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <Shield className="h-4 w-4" aria-hidden="true" />
          断路器与容灾控制台
        </button>
      </div>

      {errorMessage && (
        <output
          aria-live="polite"
          className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{errorMessage}</span>
        </output>
      )}

      {/* Tab 1: Live Search Studio */}
      {activeTab === 'search' && (
        <section className="space-y-6">
          <div className="rounded-xl border border-border/70 bg-card p-5 shadow-sm">
            <label htmlFor="hybrid-search-input" className="block text-xs font-semibold text-foreground">
              记忆检索查询表达式 (自动应用离线同义词扩展与双路召回)
            </label>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <div className="relative flex-1 min-w-[260px]">
                <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden="true" />
                <input
                  id="hybrid-search-input"
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && void handleSearch()}
                  placeholder="输入检索关键词或自然语言描述..."
                  className="w-full rounded-lg border border-border bg-background py-2 pl-9 pr-4 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  id="enable-vector-toggle"
                  type="checkbox"
                  checked={enableVector}
                  onChange={(e) => setEnableVector(e.target.checked)}
                  className="h-4 w-4 rounded border-border accent-primary focus:ring-2 focus:ring-primary"
                />
                <label htmlFor="enable-vector-toggle" className="text-xs font-medium text-foreground">
                  激活稠密向量通道
                </label>
              </div>

              <button
                type="button"
                onClick={() => void handleSearch()}
                disabled={isLoading}
                aria-label="执行双引擎混合检索"
                className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground shadow hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50"
              >
                <Search className="h-3.5 w-3.5" aria-hidden="true" />
                {isLoading ? '检索中...' : '执行检索'}
              </button>
            </div>
          </div>

          {/* Results List */}
          <div className="rounded-xl border border-border/70 bg-card p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between border-b border-border/50 pb-3">
              <div className="flex items-center gap-2">
                <Database className="h-4 w-4 text-primary" aria-hidden="true" />
                <h3 className="text-sm font-semibold text-foreground">
                  召回与排序结果 ({results.length} 条)
                </h3>
              </div>
              <span className="text-xs text-muted-foreground">
                当前运行模式：{stats.active_mode}
              </span>
            </div>

            <div className="divide-y divide-border/40">
              {results.map((hit) => {
                const percent = Math.min(100, Math.max(0, Math.round(hit.score * 100)));
                return (
                  <article key={hit.item_id} className="py-3 first:pt-0 last:pb-0">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                            {hit.rank}
                          </span>
                          <h4 className="text-sm font-semibold text-foreground">{hit.title}</h4>
                          <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] font-mono text-muted-foreground">
                            {hit.source_channel}
                          </span>
                        </div>
                        <p className="line-clamp-2 text-xs text-muted-foreground">{hit.content}</p>
                      </div>

                      <div className="min-w-[100px] text-right">
                        <div className="text-xs font-bold text-foreground">
                          {(hit.score * 100).toFixed(1)}%
                        </div>
                        <div className="mt-1">
                          <progress
                            value={percent}
                            max={100}
                            aria-label={`记忆 ${hit.item_id} 置信度`}
                            className="h-1.5 w-full overflow-hidden rounded-full [&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-value]:bg-primary [&::-moz-progress-bar]:bg-primary"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
                      <span>时效衰减：{(hit.recency_factor * 100).toFixed(0)}%</span>
                      <span>重要性：{hit.importance.toFixed(2)}</span>
                      {hit.matched_terms.length > 0 && (
                        <span>同义词命中：{hit.matched_terms.join(', ')}</span>
                      )}
                      {hit.is_degraded && (
                        <span className="font-semibold text-amber-600 dark:text-amber-400">
                          已平滑降级至纯 FTS5 兜底
                        </span>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        </section>
      )}

      {/* Tab 2: Adaptive RRF Tuner */}
      {activeTab === 'rrf' && (
        <AdaptiveRrfRankVisualizerView
          config={rrfConfig}
          onChangeConfig={setRrfConfig}
          results={results}
          onApplyRerank={() => void handleSearch()}
          isLoading={isLoading}
        />
      )}

      {/* Tab 3: Circuit Breaker Console */}
      {activeTab === 'breaker' && (
        <CircuitBreakerFallbackConsoleView
          stats={stats.circuit_breaker}
          onTripBreaker={() => void handleTripBreaker()}
          onResetBreaker={() => void handleResetBreaker()}
          isLoading={isLoading}
        />
      )}
    </div>
  );
};
