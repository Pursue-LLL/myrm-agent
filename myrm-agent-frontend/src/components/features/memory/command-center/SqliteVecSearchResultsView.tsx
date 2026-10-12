/**
 * [INPUT]
 * @/services/memory::(SqliteVecSearchResponse, SqliteVecSearchItem)
 * Lucide icons (FileText, ArrowDownRight, Tag, CheckCircle2, Shield)
 *
 * [OUTPUT]
 * Component: SqliteVecSearchResultsView
 *
 * [POS]
 * Dense vector search results and temporal decay comparison view for Item 130 SqliteVec Studio.
 * Strictly typed, zero any, a11y compliant with visible focus rings. Single file < 250 lines.
 */

'use client';

import React from 'react';
import { ArrowDownRight, CheckCircle2, FileText, Shield, Tag } from 'lucide-react';
import type { SqliteVecSearchResponse } from '@/services/memory';

interface SqliteVecSearchResultsViewProps {
  searchResponse: SqliteVecSearchResponse | null;
}

export const SqliteVecSearchResultsView: React.FC<SqliteVecSearchResultsViewProps> = ({
  searchResponse,
}) => {
  if (!searchResponse || searchResponse.results.length === 0) {
    return null;
  }

  return (
    <section
      aria-label="稠密向量近邻检索命中结果与时间衰减比对"
      className="space-y-4 rounded-xl border border-border/80 bg-card/60 p-4 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-primary" aria-hidden="true" />
          <h3 className="text-sm font-semibold text-foreground">
            检索结果与时间衰减比对 ({searchResponse.results.length} 条命中)
          </h3>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="rounded bg-muted px-2 py-0.5 text-muted-foreground">
            执行通道: {searchResponse.execution_mode}
          </span>
          <span className="rounded bg-primary/10 px-2 py-0.5 font-medium text-primary">
            {searchResponse.apply_decay ? '已应用时间半衰期衰减' : '未应用衰减'}
          </span>
        </div>
      </div>

      <div className="space-y-3">
        {searchResponse.results.map((item, idx) => {
          const rawSim = item.raw_similarity ?? item.score;
          const decayPct = item.decay_factor
            ? `${Math.round(item.decay_factor * 100)}%`
            : '100%';

          return (
            <div
              key={item.id}
              className="rounded-lg border border-border/60 bg-background/60 p-3.5 text-xs transition hover:border-border"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 font-mono text-[10px] font-bold text-primary">
                    #{idx + 1}
                  </span>
                  <span className="font-mono text-[11px] font-semibold text-foreground">
                    {item.id}
                  </span>
                </div>

                {/* Score and decay factors */}
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1">
                    <span className="text-muted-foreground">原始余弦相似度:</span>
                    <span className="font-mono font-medium text-muted-foreground">
                      {rawSim.toFixed(3)}
                    </span>
                  </div>
                  {item.decay_factor && item.decay_factor < 1.0 && (
                    <div className="flex items-center gap-0.5 text-amber-600 dark:text-amber-400">
                      <ArrowDownRight className="h-3.5 w-3.5" aria-hidden="true" />
                      <span>衰减留存: {decayPct}</span>
                    </div>
                  )}
                  <div className="rounded bg-emerald-500/10 px-2 py-0.5 font-mono font-semibold text-emerald-600 dark:text-emerald-400">
                    有效得分: {item.score.toFixed(3)}
                  </div>
                </div>
              </div>

              {/* Content text */}
              <p className="mt-2 text-sm leading-relaxed text-foreground">
                {item.content}
              </p>

              {/* Metadata attributes badges */}
              {item.metadata && Object.keys(item.metadata).length > 0 && (
                <div className="mt-2.5 flex flex-wrap items-center gap-1.5 pt-1 text-[11px] text-muted-foreground">
                  <Tag className="h-3 w-3" aria-hidden="true" />
                  {Object.entries(item.metadata).map(([k, v]) => (
                    <span
                      key={k}
                      className="rounded border border-border/40 bg-muted/50 px-1.5 py-0.5"
                    >
                      {k}: {Array.isArray(v) ? v.join(', ') : String(v)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
};
