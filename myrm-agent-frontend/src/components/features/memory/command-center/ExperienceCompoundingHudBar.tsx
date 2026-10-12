/**
 * Experience Compounding 4-Dimensional Telemetry HUD Bar.
 * Visualizes active experience fragments, synthesized Golden Rules, cold-tiered contexts,
 * and mean compounding multipliers.
 */

import React from 'react';
import { Layers, Sparkles, Snowflake, TrendingUp } from 'lucide-react';
import { ExperienceCompoundingStatsResponse } from '@/services/memory/experienceCompounding';

interface ExperienceCompoundingHudBarProps {
  stats: ExperienceCompoundingStatsResponse;
}

export const ExperienceCompoundingHudBar: React.FC<ExperienceCompoundingHudBarProps> = ({
  stats,
}) => {
  return (
    <header className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-card/60 border border-border/80 rounded-xl p-3.5 backdrop-blur-sm shadow-xs">
      {/* Metric 1: Active Hot Experiences */}
      <div className="flex items-center gap-2.5 p-2 rounded-lg bg-background/50 border border-border/40">
        <div className="p-2 rounded-md bg-emerald-500/10 text-emerald-500">
          <Layers className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] font-medium text-muted-foreground">活跃热经验</div>
          <output aria-live="polite" className="text-sm font-semibold tracking-tight text-foreground block">
            {stats.active_items} 条活跃碎片
          </output>
        </div>
      </div>

      {/* Metric 2: Synthesized Golden Rules */}
      <div className="flex items-center gap-2.5 p-2 rounded-lg bg-background/50 border border-border/40">
        <div className="p-2 rounded-md bg-amber-500/10 text-amber-500">
          <Sparkles className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] font-medium text-muted-foreground">凝练黄金准则</div>
          <output aria-live="polite" className="text-sm font-semibold tracking-tight text-foreground block">
            {stats.golden_rules_count} 项高阶规则
          </output>
        </div>
      </div>

      {/* Metric 3: Cold Tiered Contexts */}
      <div className="flex items-center gap-2.5 p-2 rounded-lg bg-background/50 border border-border/40">
        <div className="p-2 rounded-md bg-sky-500/10 text-sky-500">
          <Snowflake className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] font-medium text-muted-foreground">冷数据退火区</div>
          <output aria-live="polite" className="text-sm font-semibold tracking-tight text-foreground block">
            {stats.cold_tiered_items} 条时效沉降
          </output>
        </div>
      </div>

      {/* Metric 4: Average Compounded Multiplier */}
      <div className="flex items-center gap-2.5 p-2 rounded-lg bg-background/50 border border-border/40">
        <div className="p-2 rounded-md bg-indigo-500/10 text-indigo-500">
          <TrendingUp className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] font-medium text-muted-foreground">平均复利权重</div>
          <output aria-live="polite" className="text-sm font-semibold tracking-tight text-foreground block font-mono">
            {stats.average_compounded_weight.toFixed(2)}x
          </output>
        </div>
      </div>
    </header>
  );
};
