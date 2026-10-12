'use client';

/**
 * [INPUT]
 * @/services/memory/fourTierFts::FtsSearchResultDTO, DreamCompactionReportDTO,
 *   RunDreamCompactionRequestDTO
 *
 * [OUTPUT]
 * FourTierFtsSearchAndDreamView: Subview component rendering SQLite FTS5 millisecond full-text
 * BM25 ranked search and /dream background self-maintenance compaction console.
 *
 * [POS]
 * Subcomponent for Item 92 (Four-Tier Persistent Memory and FTS5 Self-Maintenance Suite).
 * Strict typing applied: No `any` types allowed. Single responsibility maintained.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Search, Moon, Sparkles, Clock, CheckCircle2, Scissors, Layers } from 'lucide-react';
import type {
  FtsSearchResultDTO,
  DreamCompactionReportDTO,
  RunDreamCompactionRequestDTO,
} from '@/services/memory/fourTierFts';

interface FourTierFtsSearchAndDreamViewProps {
  searchResults: FtsSearchResultDTO[];
  latestDreamReport: DreamCompactionReportDTO | null;
  onSearch: (query: string, scope?: string) => Promise<void>;
  onRunDream: (request: RunDreamCompactionRequestDTO) => Promise<void>;
}

export function FourTierFtsSearchAndDreamView({
  searchResults,
  latestDreamReport,
  onSearch,
  onRunDream,
}: FourTierFtsSearchAndDreamViewProps): React.JSX.Element {
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedScope, setSelectedScope] = useState<string>('');
  const [isSearching, setIsSearching] = useState<boolean>(false);

  // Dream compaction parameters
  const [purgeDays, setPurgeDays] = useState<number>(7);
  const [isCompacting, setIsCompacting] = useState<boolean>(false);

  const handleSearchSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setIsSearching(true);
    try {
      await onSearch(searchQuery.trim(), selectedScope || undefined);
    } finally {
      setIsSearching(false);
    }
  };

  const handleDreamSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsCompacting(true);
    try {
      await onRunDream({
        purge_progress_days: purgeDays,
      });
    } finally {
      setIsCompacting(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="four-tier-fts-search-and-dream-view">
      {/* Top Grid: FTS5 Search on Left, Dream Maintenance on Right */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Left: SQLite FTS5 Search Console */}
        <div className="rounded-lg border border-border/60 bg-accent/15 p-3.5 space-y-3">
          <div className="flex items-center gap-2 font-semibold text-xs text-foreground">
            <Search className="w-4 h-4 text-primary" />
            SQLite FTS5 毫秒级全文召回 (BM25 Ranked)
          </div>
          <p className="text-[11px] text-muted-foreground">
            独立项目虚拟表原生 BM25 检索，摒弃沉重外部库，毫秒级快速匹配四重持久记忆切片。
          </p>

          <form onSubmit={handleSearchSubmit} className="space-y-2">
            <div className="flex gap-2">
              <div className="flex-1">
                <label htmlFor="fts-query-input" className="sr-only">
                  全文检索关键词
                </label>
                <input
                  id="fts-query-input"
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="输入关键词，例如：PostgreSQL, Redis, Refactor..."
                  className="w-full rounded border border-border bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <select
                aria-label="检索分层范围"
                value={selectedScope}
                onChange={(e) => setSelectedScope(e.target.value)}
                className="rounded border border-border bg-background px-2 py-1.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">全部分层</option>
                <option value="project">项目 (Project)</option>
                <option value="session">会话 (Session)</option>
                <option value="progress">进度 (Progress)</option>
                <option value="global">全局 (Global)</option>
              </select>
              <Button
                type="submit"
                size="sm"
                disabled={isSearching || !searchQuery.trim()}
                className="text-xs shrink-0 focus:outline-none focus:ring-2 focus:ring-primary"
                data-testid="fts-search-button"
              >
                <Search className="w-3.5 h-3.5 mr-1" />
                {isSearching ? '检索中...' : '搜索'}
              </Button>
            </div>
          </form>

          {/* Search Hits List */}
          <div className="space-y-2 max-h-64 overflow-y-auto pr-1 pt-1" data-testid="fts-results-box">
            {searchResults.length === 0 ? (
              <div className="rounded border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
                暂无检索结果，请输入关键词发起毫秒全文搜索
              </div>
            ) : (
              searchResults.map((hit) => (
                <div
                  key={hit.item_id}
                  className="rounded border border-border/50 bg-background/60 p-2.5 text-xs space-y-1"
                  data-testid={`fts-hit-${hit.item_id}`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-foreground line-clamp-1">{hit.title}</span>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <Badge variant="outline" className="text-[10px] uppercase">
                        {hit.scope}
                      </Badge>
                      <span className="font-mono text-[10px] text-muted-foreground">
                        BM25: {hit.bm25_rank}
                      </span>
                    </div>
                  </div>
                  <p className="text-[11px] text-muted-foreground line-clamp-2">
                    {hit.snippet || hit.content}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right: /dream Self-Maintenance Compaction */}
        <div className="rounded-lg border border-indigo-500/30 bg-indigo-500/5 p-3.5 space-y-3">
          <div className="flex items-center gap-2 font-semibold text-xs text-foreground">
            <Moon className="w-4 h-4 text-indigo-400" />
            /dream 周期性与按需梦境自维护压缩
          </div>
          <p className="text-[11px] text-muted-foreground">
            对标小米 MiMo Code 7 天自维护循环：合并碎片笔记、消除过时矛盾条目、清除过期任务进度。
          </p>

          <form onSubmit={handleDreamSubmit} className="space-y-2 rounded border border-border/50 bg-background/50 p-2.5 text-xs">
            <div className="flex items-center justify-between gap-2">
              <label htmlFor="purge-days-input" className="text-muted-foreground">
                进度记忆清理阈值（天）:
              </label>
              <input
                id="purge-days-input"
                type="number"
                min="1"
                max="90"
                value={purgeDays}
                onChange={(e) => setPurgeDays(Number(e.target.value))}
                className="w-20 rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div className="flex justify-end pt-1">
              <Button
                type="submit"
                size="sm"
                disabled={isCompacting}
                className="text-xs bg-indigo-600 hover:bg-indigo-700 text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                data-testid="trigger-dream-compaction-button"
              >
                <Sparkles className="w-3.5 h-3.5 mr-1" />
                {isCompacting ? '压缩整理中...' : '立即执行 /dream 梦境维护'}
              </Button>
            </div>
          </form>

          {/* Latest Compaction Report */}
          <div className="space-y-2">
            <div className="text-[11px] font-semibold text-foreground flex items-center gap-1">
              <Layers className="w-3.5 h-3.5 text-indigo-400" />
              最新梦境维护重构简报 (Maintenance Report)
            </div>

            {latestDreamReport ? (
              <div
                className="rounded border border-indigo-500/20 bg-background/70 p-2.5 text-xs space-y-2"
                data-testid="dream-report-box"
              >
                <div className="flex items-center justify-between text-[11px] text-muted-foreground font-mono">
                  <span>ID: {latestDreamReport.dream_id}</span>
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {latestDreamReport.duration_ms.toFixed(1)}ms
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div className="rounded bg-accent/30 p-1.5 flex items-center justify-between">
                    <span className="text-muted-foreground">扫描记忆项:</span>
                    <span className="font-semibold text-foreground">{latestDreamReport.scanned_items_count}</span>
                  </div>
                  <div className="rounded bg-accent/30 p-1.5 flex items-center justify-between">
                    <span className="text-muted-foreground flex items-center gap-1">
                      <Sparkles className="w-3 h-3 text-indigo-400" />
                      合并碎片:
                    </span>
                    <span className="font-semibold text-indigo-500">{latestDreamReport.merged_items_count}</span>
                  </div>
                  <div className="rounded bg-accent/30 p-1.5 flex items-center justify-between">
                    <span className="text-muted-foreground flex items-center gap-1">
                      <Scissors className="w-3 h-3 text-amber-500" />
                      剪枝清理:
                    </span>
                    <span className="font-semibold text-amber-500">{latestDreamReport.pruned_items_count}</span>
                  </div>
                  <div className="rounded bg-accent/30 p-1.5 flex items-center justify-between">
                    <span className="text-muted-foreground flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                      有效保留:
                    </span>
                    <span className="font-semibold text-emerald-500">{latestDreamReport.retained_items_count}</span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="rounded border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
                暂无执行报告，可点击上方按钮立即启动一次 /dream 周期
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
