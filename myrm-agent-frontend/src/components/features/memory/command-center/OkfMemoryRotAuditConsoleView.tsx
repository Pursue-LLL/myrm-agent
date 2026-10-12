'use client';

/**
 * [INPUT]
 * @/services/memory/gitOkf::OKFValidationReportDTO, OKFSearchResultDTO, OKFSearchRequestDTO
 *
 * [OUTPUT]
 * OkfMemoryRotAuditConsoleView: Subview component rendering OKF memory rot prevention audits,
 * human-agent anti-tamper trust balance findings, and sub-millisecond in-memory BM25 retrieval.
 *
 * [POS]
 * Subcomponent for Item 95 (Git-Native Project Knowledge Bundle & Memory Rot Prevention Suite).
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { ShieldCheck, ShieldAlert, Search, RefreshCw, AlertTriangle, UserCheck, Flame, Scale } from 'lucide-react';
import type {
  OKFValidationReportDTO,
  OKFSearchResultDTO,
  OKFSearchRequestDTO,
} from '@/services/memory/gitOkf';

interface OkfMemoryRotAuditConsoleViewProps {
  report: OKFValidationReportDTO | null;
  searchResults: OKFSearchResultDTO[];
  onValidateBundle: () => Promise<void>;
  onSearchConcepts: (request: OKFSearchRequestDTO) => Promise<void>;
}

export function OkfMemoryRotAuditConsoleView({
  report,
  searchResults,
  onValidateBundle,
  onSearchConcepts,
}: OkfMemoryRotAuditConsoleViewProps): React.JSX.Element {
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [filterGov, setFilterGov] = useState<string>('');
  const [isValidating, setIsValidating] = useState<boolean>(false);
  const [isSearching, setIsSearching] = useState<boolean>(false);

  const handleValidateClick = async () => {
    setIsValidating(true);
    try {
      await onValidateBundle();
    } finally {
      setIsValidating(false);
    }
  };

  const handleSearchSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      return;
    }
    setIsSearching(true);
    try {
      await onSearchConcepts({
        query: searchQuery.trim(),
        filter_governance: filterGov || undefined,
      });
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="okf-memory-rot-audit-console-view">
      {/* Top Banner: Memory Rot & Trust Equilibrium Explanation */}
      <div className="rounded-lg border border-border/60 bg-accent/15 p-3 text-xs space-y-1.5">
        <div className="font-semibold text-foreground flex items-center gap-1.5">
          <Scale className="w-4 h-4 text-primary" />
          防腐烂显式保质期与人机防篡改信任天平 (Rot Prevention & Trust Balance)
        </div>
        <p className="text-muted-foreground leading-relaxed text-[11px]">
          根据 Google OKF v0.2 标准：
          <span className="text-foreground font-semibold"> 显式保质期 (stale_after)</span> 零 LLM 毫秒级门禁校验，拒绝过时陈旧规范误导 Agent；
          <span className="text-foreground font-semibold"> 人机防篡改机制</span> 严格保护人类架构师核准规范（verified: human），Agent 无法私自推翻人类签名。
        </p>
      </div>

      {/* Grid: Audit Findings Report & In-Memory BM25 Searcher */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Left: Validation & Trust Audit Report */}
        <div className="rounded-lg border border-border/60 bg-accent/15 p-3.5 space-y-3">
          <div className="flex items-center justify-between border-b border-border/40 pb-2">
            <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-emerald-500" />
              合规与防腐烂门禁巡检报告
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleValidateClick}
              disabled={isValidating}
              aria-label="重新执行防腐烂与防篡改门禁巡检"
              className="text-xs h-7 focus:outline-none focus:ring-2 focus:ring-primary flex items-center gap-1"
              data-testid="btn-validate-okf-bundle"
            >
              <RefreshCw className={`w-3 h-3 ${isValidating ? 'animate-spin' : ''}`} />
              {isValidating ? '巡检中...' : '重新巡检'}
            </Button>
          </div>

          {report ? (
            <div className="space-y-2 text-xs" data-testid="okf-validation-report-box">
              {/* Metrics row */}
              <div className="grid grid-cols-3 gap-2 text-[11px]">
                <div className="rounded border border-border/50 bg-background/60 p-2">
                  <span className="text-muted-foreground block text-[10px]">概念卡片总量</span>
                  <span className="text-sm font-bold text-foreground font-mono" data-testid="metric-concept-count">
                    {report.concept_count} 篇
                  </span>
                </div>
                <div className="rounded border border-border/50 bg-background/60 p-2">
                  <span className="text-muted-foreground block text-[10px]">已过期腐烂卡片</span>
                  <span className="text-sm font-bold text-amber-600 font-mono" data-testid="metric-stale-count">
                    {report.stale_count} 篇
                  </span>
                </div>
                <div className="rounded border border-border/50 bg-background/60 p-2">
                  <span className="text-muted-foreground block text-[10px]">被篡改人类签名</span>
                  <span className="text-sm font-bold text-rose-600 font-mono" data-testid="metric-superseded-trust">
                    {report.superseded_trust_count} 项
                  </span>
                </div>
              </div>

              {/* Status pill */}
              <div className="rounded bg-background/50 border border-border/40 p-2 flex items-center justify-between text-[11px]">
                <span className="text-muted-foreground">门禁审核裁决：</span>
                <Badge
                  variant={report.gate_passed ? 'default' : 'destructive'}
                  className="text-[10px]"
                  data-testid="badge-gate-passed"
                >
                  {report.gate_passed ? '门禁通过 (PASSED)' : '门禁拦截 (BLOCKED)'}
                </Badge>
              </div>

              {/* Warnings & Findings lists */}
              {report.warnings.length > 0 && (
                <div className="space-y-1 pt-1">
                  <span className="text-[10px] text-muted-foreground font-medium flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3 text-amber-500" />
                    防腐烂预警 ({report.warnings.length} 项):
                  </span>
                  <div className="max-h-24 overflow-y-auto space-y-1">
                    {report.warnings.map((w, i) => (
                      <div key={i} className="text-[10px] text-amber-700 dark:text-amber-400 font-mono bg-amber-500/10 p-1 rounded">
                        {w}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {report.gate_findings.length > 0 && (
                <div className="space-y-1 pt-1">
                  <span className="text-[10px] text-muted-foreground font-medium flex items-center gap-1">
                    <ShieldAlert className="w-3 h-3 text-rose-500" />
                    人机防篡改门禁违规 ({report.gate_findings.length} 项):
                  </span>
                  <div className="max-h-24 overflow-y-auto space-y-1">
                    {report.gate_findings.map((f, i) => (
                      <div key={i} className="text-[10px] text-rose-700 dark:text-rose-400 font-mono bg-rose-500/10 p-1 rounded">
                        {f}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="py-8 text-center text-xs text-muted-foreground">
              尚未运行门禁审核，可点击右上角按钮开始巡检。
            </div>
          )}
        </div>

        {/* Right: In-Memory BM25 Lexical Retrieval Console */}
        <div className="rounded-lg border border-border/60 bg-accent/15 p-3.5 space-y-3">
          <div className="flex items-center gap-2 font-semibold text-xs text-foreground border-b border-border/40 pb-2">
            <Search className="w-4 h-4 text-primary" />
            亚毫秒纯内存 BM25 词法检索 (In-Memory Search)
          </div>

          <form onSubmit={handleSearchSubmit} className="space-y-2 text-xs" data-testid="okf-search-form">
            <div className="flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="检索规范、代码约定或架构决议..."
                aria-label="输入检索词"
                className="flex-1 rounded border border-border bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <select
                value={filterGov}
                onChange={(e) => setFilterGov(e.target.value)}
                aria-label="筛选治理层级"
                className="rounded border border-border bg-background px-2 py-1.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">全部</option>
                <option value="constraint">强制约束</option>
                <option value="hold">人工签署</option>
                <option value="context">背景知识</option>
              </select>
            </div>

            <div className="flex justify-end">
              <Button
                type="submit"
                size="sm"
                disabled={isSearching || !searchQuery.trim()}
                aria-label="发起 BM25 词法检索"
                className="text-xs h-7 focus:outline-none focus:ring-2 focus:ring-primary flex items-center gap-1"
                data-testid="btn-trigger-okf-search"
              >
                <Search className="w-3 h-3" />
                {isSearching ? '检索中...' : 'BM25 检索 (<300µs)'}
              </Button>
            </div>
          </form>

          {/* Search Hits List */}
          <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1" data-testid="okf-search-results-list">
            {searchResults.length === 0 ? (
              <div className="rounded border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
                暂无检索命中结果，请输入关键词发起检索。
              </div>
            ) : (
              searchResults.map((hit) => (
                <div
                  key={hit.concept_id}
                  className="rounded border border-border/50 bg-background/70 p-2 text-xs space-y-1"
                  data-testid={`okf-hit-${hit.concept_id}`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-foreground truncate">{hit.title}</span>
                    <div className="flex items-center gap-1">
                      {hit.is_stale && (
                        <Badge variant="destructive" className="text-[9px]">
                          STALE
                        </Badge>
                      )}
                      <Badge variant="outline" className="text-[10px] font-mono">
                        BM25: {hit.score.toFixed(2)}
                      </Badge>
                    </div>
                  </div>
                  <p className="text-[11px] text-muted-foreground line-clamp-1">{hit.description}</p>
                  <div className="flex items-center justify-between text-[10px] text-muted-foreground font-mono">
                    <span>{hit.concept_id}</span>
                    <span>命中字段: {hit.matched_fields.join(', ')}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
