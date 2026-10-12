'use client';

/**
 * [INPUT]
 * @/services/memory/conversationLineageDefense::HydratedHitDTO, LineageDedupAuditReportDTO,
 *   LineageDefenseSearchRequestDTO
 *
 * [OUTPUT]
 * AutomationDemotionAuditConsoleView: Subview providing interactive test queries, source demotion
 * tuning, Top-1 expanded window vs Top-2..N compact cards inspection, and token savings breakdown.
 *
 * [POS]
 * Subcomponent for Item 97 (LineageDedupRecallBlindnessDefenseAndAutomationDemotionSuite).
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Search, Sparkles, TrendingDown, Eye, CheckCircle2, AlertCircle } from 'lucide-react';
import type {
  HydratedHitDTO,
  LineageDedupAuditReportDTO,
  LineageDefenseSearchRequestDTO,
} from '@/services/memory/conversationLineageDefense';

interface AutomationDemotionAuditConsoleViewProps {
  hits: HydratedHitDTO[];
  auditReport: LineageDedupAuditReportDTO | null;
  onExecuteSearch: (request: LineageDefenseSearchRequestDTO) => Promise<void>;
}

export function AutomationDemotionAuditConsoleView({
  hits,
  auditReport,
  onExecuteSearch,
}: AutomationDemotionAuditConsoleViewProps): React.JSX.Element {
  const [queryInput, setQueryInput] = useState<string>('authentication token validation');
  const [includeInternal, setIncludeInternal] = useState<boolean>(false);
  const [cronMultiplier, setCronMultiplier] = useState<number>(0.45);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      await onExecuteSearch({
        query: queryInput.trim(),
        include_internal: includeInternal,
        cron_weight_multiplier: cronMultiplier,
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="automation-demotion-audit-console-view">
      {/* Search and Parameter Tuning Bar */}
      <form
        onSubmit={handleSubmit}
        className="rounded-lg border border-border/60 bg-accent/15 p-3.5 space-y-3 text-xs"
        data-testid="lineage-search-form"
      >
        <div className="flex flex-col sm:flex-row gap-2">
          <div className="flex-1 space-y-1">
            <label htmlFor="input-defense-query" className="font-semibold text-foreground flex items-center gap-1.5">
              <Search className="w-3.5 h-3.5 text-primary" />
              检索测试语句 (Query)：
            </label>
            <input
              id="input-defense-query"
              type="text"
              value={queryInput}
              onChange={(e) => setQueryInput(e.target.value)}
              placeholder="输入查询语句，验证来源感知降权与自适应展开..."
              aria-label="会话检索测试语句"
              className="w-full rounded border border-border bg-background px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <div className="flex items-end">
            <Button
              type="submit"
              size="sm"
              disabled={isLoading || !queryInput.trim()}
              aria-label="执行来源降权与血统去重检索"
              className="h-8 gap-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary w-full sm:w-auto"
              data-testid="btn-execute-defense-search"
            >
              <Sparkles className="w-3.5 h-3.5" />
              {isLoading ? '检索计算中...' : '运行防盲区检索'}
            </Button>
          </div>
        </div>

        {/* Controls Row */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-1 border-t border-border/40 text-[11px]">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={includeInternal}
              onChange={(e) => setIncludeInternal(e.target.checked)}
              aria-label="包含内部 Worker 会话"
              className="rounded border-border text-primary focus:ring-primary h-3.5 w-3.5"
            />
            <span className="text-foreground">透出内部 Worker 会话 (默认自动隐蔽降噪)</span>
          </label>

          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Cron 降权惩罚系数：</span>
            <select
              value={cronMultiplier}
              onChange={(e) => setCronMultiplier(parseFloat(e.target.value))}
              aria-label="选择 Cron 降权系数"
              className="rounded border border-border bg-background px-2 py-0.5 text-foreground font-mono focus:outline-none focus:ring-2 focus:ring-primary text-[11px]"
            >
              <option value="0.3">0.30 (强惩罚)</option>
              <option value="0.45">0.45 (标准推荐)</option>
              <option value="0.6">0.60 (轻惩罚)</option>
              <option value="1.0">1.00 (无惩罚 / 传统BM25)</option>
            </select>
          </div>
        </div>
      </form>

      {/* Audit Report Banner */}
      {auditReport && (
        <div
          className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs grid grid-cols-2 sm:grid-cols-4 gap-2"
          data-testid="audit-report-banner"
        >
          <div className="space-y-0.5">
            <span className="text-muted-foreground text-[10px]">交互会话置顶率</span>
            <div className="text-base font-bold text-blue-600 dark:text-blue-400">
              {(auditReport.interactive_top1_ratio * 100).toFixed(0)}%
            </div>
          </div>
          <div className="space-y-0.5">
            <span className="text-muted-foreground text-[10px]">Cron 自动化降权</span>
            <div className="text-base font-bold text-amber-600 dark:text-amber-400">
              {auditReport.demoted_cron_count} 项
            </div>
          </div>
          <div className="space-y-0.5">
            <span className="text-muted-foreground text-[10px]">隐蔽内部杂音</span>
            <div className="text-base font-bold text-purple-600 dark:text-purple-400">
              {auditReport.hidden_internal_count} 项
            </div>
          </div>
          <div className="space-y-0.5">
            <span className="text-muted-foreground text-[10px]">Token 开销节约</span>
            <div className="text-base font-bold text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
              <TrendingDown className="w-4 h-4" />
              {auditReport.token_saving_percent}%
            </div>
          </div>
        </div>
      )}

      {/* Progressive Hydrated Hits List */}
      <div className="space-y-2.5">
        <div className="flex items-center justify-between text-xs font-semibold text-foreground">
          <span>自适应视窗水合检索结果 ({hits.length} 项命中)</span>
          <span className="text-muted-foreground text-[11px]">
            Top 1 展开完整多轮视窗 • Top 2~N 紧凑卡片节约 70%+ Token
          </span>
        </div>

        {hits.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border/70 p-8 text-center text-xs text-muted-foreground">
            无匹配会话命中，请调整查询语句或降低惩罚系数。
          </div>
        ) : (
          hits.map((hit, index) => {
            const isTop1 = index === 0;
            return (
              <div
                key={hit.session_id}
                className={`rounded-lg border p-3 text-xs space-y-2 transition-colors ${
                  isTop1
                    ? 'border-primary/50 bg-primary/5'
                    : 'border-border/60 bg-background/60 hover:bg-accent/20'
                }`}
                data-testid={`hit-item-${hit.session_id}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-muted-foreground">
                      #{index + 1}
                    </span>
                    <span className="font-semibold text-foreground">{hit.title}</span>
                  </div>

                  <div className="flex items-center gap-1.5">
                    {hit.is_demoted && (
                      <Badge variant="destructive" className="text-[9px] px-1.5 py-0 flex items-center gap-0.5">
                        <AlertCircle className="w-2.5 h-2.5" />
                        已降权 (Demoted)
                      </Badge>
                    )}
                    <Badge
                      variant={isTop1 ? 'default' : 'outline'}
                      className="text-[9px] uppercase font-mono"
                    >
                      {hit.detail_level === 'expanded_window' ? 'Expanded Window' : 'Compact Card'}
                    </Badge>
                    <span className="text-[10px] text-muted-foreground font-mono">
                      ~{hit.token_estimate} tokens
                    </span>
                  </div>
                </div>

                {/* Display content or expanded window messages */}
                {hit.detail_level === 'expanded_window' ? (
                  <div className="space-y-1.5 rounded border border-border/50 bg-background/80 p-2.5">
                    <div className="flex items-center gap-1 text-[10px] font-semibold text-primary">
                      <Eye className="w-3 h-3" />
                      Top 1 深度对话上下文视窗展开 (±5 Turns)：
                    </div>
                    {hit.window_messages.length > 0 ? (
                      <div className="space-y-1 text-[11px] font-mono leading-relaxed text-foreground">
                        {hit.window_messages.map((turn, tIdx) => (
                          <div key={tIdx} className="rounded bg-accent/20 p-1.5 border border-border/30">
                            {turn}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-[11px] text-muted-foreground font-mono">
                        {hit.content_snippet}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="rounded border border-border/40 bg-accent/10 px-2.5 py-1.5 text-[11px] text-muted-foreground font-mono flex items-center justify-between">
                    <span className="truncate max-w-[420px]">{hit.content_snippet}</span>
                    <span className="text-[10px] text-emerald-600 flex items-center gap-0.5 shrink-0">
                      <CheckCircle2 className="w-3 h-3" />
                      紧凑卡片已节约 80% Token
                    </span>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
