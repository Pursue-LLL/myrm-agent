/**
 * [INPUT]
 * @/services/memory/autoMemoryConsolidation::OverallGatingReportDTO
 * lucide-react::Clock, ShieldCheck, ShieldAlert, Sparkles, Database
 *
 * [OUTPUT]
 * AutoMemoryGatingHudBar: 4-dimensional real-time HUD bar for session admission.
 *
 * [POS]
 * Visual metric HUD for Item 123 auto-consolidation studio.
 * Strict typing: No `any`. Single file < 200 lines.
 */

import React from 'react';
import { Clock, ShieldCheck, ShieldAlert, Sparkles, Database } from 'lucide-react';
import type { OverallGatingReportDTO } from '@/services/memory/autoMemoryConsolidation';

interface AutoMemoryGatingHudBarProps {
  report: OverallGatingReportDTO;
}

export const AutoMemoryGatingHudBar: React.FC<AutoMemoryGatingHudBarProps> = ({ report }) => {
  const { should_consolidate, idle_state, turn_decision, budget_decision } = report;

  return (
    <section
      aria-label="自动记忆沉淀四维门禁监控仪表盘"
      className="grid grid-cols-1 md:grid-cols-4 gap-3 bg-secondary/20 p-3.5 rounded-lg border border-border/40 text-xs"
    >
      {/* 1. 准入判定总状态 */}
      <div className="flex flex-col gap-1.5 p-2 rounded bg-background/60 border border-border/30">
        <div className="flex items-center justify-between text-muted-foreground">
          <span className="font-medium flex items-center gap-1.5">
            {should_consolidate ? (
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
            ) : (
              <ShieldAlert className="w-3.5 h-3.5 text-amber-500" />
            )}
            门禁综合准入
          </span>
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
              should_consolidate
                ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30'
                : 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30'
            }`}
          >
            {should_consolidate ? '准入放行' : '门禁拦截'}
          </span>
        </div>
        <div className="text-sm font-semibold truncate text-foreground">
          {should_consolidate ? '符合自动沉淀标准' : '条件未满足（挂起）'}
        </div>
        <div className="text-[11px] text-muted-foreground truncate" title={report.final_rationale}>
          {report.final_rationale}
        </div>
      </div>

      {/* 2. 闲置窗口感知 */}
      <div className="flex flex-col gap-1.5 p-2 rounded bg-background/60 border border-border/30">
        <div className="flex items-center justify-between text-muted-foreground">
          <span className="font-medium flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-blue-500" />
            会话闲置感知
          </span>
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
              idle_state.is_idle_triggered
                ? 'bg-blue-500/15 text-blue-600 dark:text-blue-400'
                : 'bg-muted text-muted-foreground'
            }`}
          >
            {idle_state.is_idle_triggered ? '闲置达标' : '活跃中'}
          </span>
        </div>
        <div className="text-sm font-semibold text-foreground">
          {idle_state.idle_seconds}s / {idle_state.idle_threshold_seconds}s
        </div>
        <div className="text-[11px] text-muted-foreground truncate" title={idle_state.reason}>
          {idle_state.reason}
        </div>
      </div>

      {/* 3. 对话轮数与信息密度 */}
      <div className="flex flex-col gap-1.5 p-2 rounded bg-background/60 border border-border/30">
        <div className="flex items-center justify-between text-muted-foreground">
          <span className="font-medium flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-purple-500" />
            轮数与信息增益
          </span>
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
              turn_decision.passed
                ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
                : 'bg-rose-500/15 text-rose-600 dark:text-rose-400'
            }`}
          >
            {turn_decision.passed ? '达标' : '过短/闲聊'}
          </span>
        </div>
        <div className="text-sm font-semibold text-foreground">
          {turn_decision.turn_count} 轮 · 密度 {(turn_decision.info_density * 100).toFixed(1)}%
        </div>
        <div className="text-[11px] text-muted-foreground truncate" title={turn_decision.reason}>
          {turn_decision.reason}
        </div>
      </div>

      {/* 4. Token 预算保护与开销比 */}
      <div className="flex flex-col gap-1.5 p-2 rounded bg-background/60 border border-border/30">
        <div className="flex items-center justify-between text-muted-foreground">
          <span className="font-medium flex items-center gap-1.5">
            <Database className="w-3.5 h-3.5 text-amber-500" />
            预算保护看门狗
          </span>
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
              budget_decision.passed
                ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
                : 'bg-rose-500/15 text-rose-600 dark:text-rose-400'
            }`}
          >
            {budget_decision.passed ? '安全' : '预算受限'}
          </span>
        </div>
        <div className="text-sm font-semibold text-foreground">
          余量 {budget_decision.remaining_tokens.toLocaleString()} · 开销 {(budget_decision.cost_ratio * 100).toFixed(1)}%
        </div>
        <div className="text-[11px] text-muted-foreground truncate" title={budget_decision.reason}>
          预估消耗 {budget_decision.estimated_cost_tokens} Tokens
        </div>
      </div>
    </section>
  );
};
