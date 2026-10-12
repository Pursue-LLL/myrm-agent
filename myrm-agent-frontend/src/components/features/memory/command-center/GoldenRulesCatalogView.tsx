/**
 * Golden Rules Catalog and Lineage Rollback View.
 * Displays higher-order principles distilled from scattered micro-fragments with parent-child lineage,
 * and allows users to decondense rules back to individual fragments.
 */

import React from 'react';
import { Sparkles, Undo2, Layers, ShieldCheck } from 'lucide-react';
import { GoldenRuleDTO } from '@/services/memory/experienceCompounding';

interface GoldenRulesCatalogViewProps {
  rules: GoldenRuleDTO[];
  onDecondense: (ruleId: string) => Promise<void>;
  isProcessing: boolean;
}

export const GoldenRulesCatalogView: React.FC<GoldenRulesCatalogViewProps> = ({
  rules,
  onDecondense,
  isProcessing,
}) => {
  return (
    <section className="bg-card/70 border border-border/70 rounded-xl p-4 shadow-xs space-y-3.5">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-amber-500/10 text-amber-500">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">高阶黄金准则库</h3>
            <p className="text-xs text-muted-foreground">
              由高频经验碎片语义聚类自动提炼，Token 压缩比达 50% 以上，支持双层谱系无损回退
            </p>
          </div>
        </div>
        <span className="text-xs px-2.5 py-1 rounded-full font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/30">
          {rules.length} 项已凝练规则
        </span>
      </header>

      {rules.length === 0 ? (
        <div className="p-6 text-center border border-dashed border-border/60 rounded-xl space-y-1.5">
          <Layers className="w-6 h-6 text-muted-foreground/60 mx-auto" />
          <div className="text-xs font-semibold text-foreground">暂无凝练的黄金准则</div>
          <p className="text-xs text-muted-foreground">
            当同一领域主题下积累 2 条以上语义重合的经验碎片时，点击下方“一键语义凝练”即可聚合生成。
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {rules.map((rule) => (
            <article
              key={rule.rule_id}
              className="p-3.5 rounded-xl bg-background/70 border border-border/60 space-y-2.5 hover:border-border transition-colors"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-bold px-2 py-0.5 rounded-md bg-secondary text-secondary-foreground border border-border/40 uppercase">
                    {rule.topic}
                  </span>
                  <span className="text-[11px] text-muted-foreground font-mono">
                    {rule.rule_id}
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3" />
                    置信度 {(rule.confidence_score * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              {/* Canonical Rule Statement */}
              <div className="text-xs font-medium text-foreground leading-relaxed pl-2.5 border-l-2 border-amber-500">
                {rule.rule_statement}
              </div>

              {/* Rationale and Source Lineage */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pt-1 border-t border-border/40 text-xs text-muted-foreground">
                <span className="text-[11px]">{rule.rationale}</span>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[11px] bg-muted/60 px-1.5 py-0.5 rounded-md">
                    包含 {rule.source_fragment_ids.length} 条原始碎片
                  </span>
                  <button
                    type="button"
                    disabled={isProcessing}
                    onClick={() => onDecondense(rule.rule_id)}
                    className="text-xs px-2.5 py-1 rounded-lg bg-muted hover:bg-muted/80 text-foreground transition-colors flex items-center gap-1 focus:outline-hidden focus:ring-2 focus:ring-primary disabled:opacity-50"
                  >
                    <Undo2 className="w-3 h-3 text-muted-foreground" />
                    回退解散
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
};
