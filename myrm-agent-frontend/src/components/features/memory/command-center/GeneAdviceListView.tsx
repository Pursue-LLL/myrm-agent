/**
 * [INPUT]
 * - @/services/memory/experienceGene: GeneMutationAdviceResponse
 * - @/components/primitives/badge: Badge
 *
 * [OUTPUT]
 * - GeneAdviceListView: Sub-component rendering causal gene-informed mutation advice.
 *
 * [POS]
 * Sub-component for GeneEvolutionInspectorCard under command-center.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React from 'react';
import { AlertCircle, CheckCircle2, Dna, ShieldAlert, Sparkles } from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import type { GeneMutationAdviceResponse } from '@/services/memory/experienceGene';

interface GeneAdviceListViewProps {
  advices: GeneMutationAdviceResponse[];
}

export function GeneAdviceListView({ advices }: GeneAdviceListViewProps) {
  if (advices.length === 0) {
    return (
      <div className="rounded border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
        未匹配到相关因果经验基因，当前任务特征属于全新探索路径
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      <div className="text-[11px] font-medium text-muted-foreground flex items-center justify-between">
        <span>规划期命中经验基因建议 ({advices.length})</span>
      </div>
      <div className="max-h-60 space-y-2.5 overflow-y-auto pr-1">
        {advices.map((adv) => {
          const isNegative = adv.polarity === 'negative';
          return (
            <div
              key={adv.gene_id}
              className="rounded-md border border-border/70 bg-card p-3 text-xs transition"
            >
              <div className="flex flex-wrap items-center justify-between gap-1.5 pb-2 border-b border-border/50">
                <div className="flex items-center gap-1.5 font-mono text-[11px] text-foreground font-semibold">
                  <Dna className="h-3.5 w-3.5 text-primary" />
                  <span>{adv.gene_id}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Badge
                    variant="outline"
                    className={
                      isNegative
                        ? 'border-destructive/40 text-destructive bg-destructive/10'
                        : 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10'
                    }
                  >
                    {isNegative ? '负向避坑基因' : '正向策略基因'}
                  </Badge>
                  <span className="text-[10px] text-muted-foreground font-mono">
                    置信度: {(adv.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              {/* 命中征兆信号 */}
              <div className="mt-2 flex flex-wrap items-center gap-1">
                <span className="text-[10px] text-muted-foreground">触发征兆:</span>
                {adv.matched_signals.map((sig) => (
                  <Badge key={sig} variant="secondary" className="px-1.5 py-0 text-[10px] font-mono">
                    {sig}
                  </Badge>
                ))}
              </div>

              {/* 已证伪的死胡同路径 */}
              {adv.refuted_paths.length > 0 && (
                <div className="mt-2 rounded bg-amber-500/10 p-2 text-amber-700 dark:text-amber-400 border border-amber-500/20">
                  <div className="flex items-center gap-1 text-[11px] font-medium">
                    <ShieldAlert className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400 shrink-0" />
                    <span>已证伪的死胡同路径 (警惕重复踩坑):</span>
                  </div>
                  <ul className="mt-1 list-disc list-inside space-y-0.5 text-[10px] text-muted-foreground pl-1 font-mono">
                    {adv.refuted_paths.map((p, idx) => (
                      <li key={idx}>{p}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* 验证解决路径 */}
              <div className="mt-2 flex items-start gap-1.5 rounded bg-accent/40 p-2 text-foreground">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
                <div className="text-[11px]">
                  <strong>验证解决路径:</strong> {adv.recommended_resolution}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
