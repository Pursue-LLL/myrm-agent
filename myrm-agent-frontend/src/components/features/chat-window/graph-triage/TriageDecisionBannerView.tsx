import React from 'react';
import type { TriageDecision, TriageVerdictType } from './types';

interface TriageDecisionBannerViewProps {
  decision: TriageDecision;
  onSelectScenario: (scenario: 'simple' | 'exploratory' | 'sequential' | 'parallel') => void;
}

const VERDICT_THEMES: Record<
  TriageVerdictType,
  { badge: string; bgClass: string; borderClass: string; textClass: string; icon: string }
> = {
  admit_graph: {
    badge: '准许进入图工程 (ADMIT)',
    bgClass: 'bg-emerald-50 dark:bg-emerald-950/30',
    borderClass: 'border-emerald-300 dark:border-emerald-800',
    textClass: 'text-emerald-800 dark:text-emerald-200',
    icon: '🚀',
  },
  reject_to_single_agent: {
    badge: '拦截并降级为单 Agent (REJECT)',
    bgClass: 'bg-amber-50 dark:bg-amber-950/30',
    borderClass: 'border-amber-300 dark:border-amber-800',
    textClass: 'text-amber-800 dark:text-amber-200',
    icon: '⚡',
  },
  reject_to_conversational: {
    badge: '拦截并保持交互对话 (REJECT)',
    bgClass: 'bg-sky-50 dark:bg-sky-950/30',
    borderClass: 'border-sky-300 dark:border-sky-800',
    textClass: 'text-sky-800 dark:text-sky-200',
    icon: '💬',
  },
  reject_to_linear_pipeline: {
    badge: '拦截并保持线性流水线 (REJECT)',
    bgClass: 'bg-purple-50 dark:bg-purple-950/30',
    borderClass: 'border-purple-300 dark:border-purple-800',
    textClass: 'text-purple-800 dark:text-purple-200',
    icon: '🔗',
  },
};

export const TriageDecisionBannerView: React.FC<TriageDecisionBannerViewProps> = ({
  decision,
  onSelectScenario,
}) => {
  const theme = VERDICT_THEMES[decision.verdict];

  return (
    <section
      aria-label="图模式准入评估门禁决策"
      className={`rounded-lg border p-4 ${theme.bgClass} ${theme.borderClass} transition-colors duration-200`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200/50 pb-3 dark:border-gray-800/50">
        <div className="flex items-center gap-2">
          <span className="text-xl" aria-hidden="true">
            {theme.icon}
          </span>
          <span
            data-testid="triage-verdict-badge"
            className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${theme.textClass} bg-white/70 shadow-sm dark:bg-black/40`}
          >
            {theme.badge}
          </span>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            类别: <strong className="font-mono">{decision.category}</strong>
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500 dark:text-gray-400">场景试演:</span>
          <div className="flex flex-wrap gap-1">
            <button
              type="button"
              onClick={() => onSelectScenario('simple')}
              className="rounded bg-white/80 px-2 py-0.5 text-xs font-medium text-gray-700 hover:bg-white dark:bg-gray-800 dark:text-gray-200"
              data-testid="scenario-simple-btn"
            >
              错别字单步
            </button>
            <button
              type="button"
              onClick={() => onSelectScenario('exploratory')}
              className="rounded bg-white/80 px-2 py-0.5 text-xs font-medium text-gray-700 hover:bg-white dark:bg-gray-800 dark:text-gray-200"
              data-testid="scenario-exploratory-btn"
            >
              头脑风暴探索
            </button>
            <button
              type="button"
              onClick={() => onSelectScenario('sequential')}
              className="rounded bg-white/80 px-2 py-0.5 text-xs font-medium text-gray-700 hover:bg-white dark:bg-gray-800 dark:text-gray-200"
              data-testid="scenario-sequential-btn"
            >
              严格串行
            </button>
            <button
              type="button"
              onClick={() => onSelectScenario('parallel')}
              className="rounded bg-white/80 px-2 py-0.5 text-xs font-medium text-gray-700 hover:bg-white dark:bg-gray-800 dark:text-gray-200"
              data-testid="scenario-parallel-btn"
            >
              重型并行(准入)
            </button>
          </div>
        </div>
      </div>

      <div className="mt-3">
        <p className="text-sm font-medium leading-relaxed text-gray-800 dark:text-gray-100">
          {decision.reason}
        </p>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div className="rounded bg-white/60 p-2 dark:bg-black/30">
          <span className="block text-[11px] text-gray-500 dark:text-gray-400">推荐执行模式</span>
          <span className="text-xs font-semibold text-gray-900 dark:text-gray-100">
            {decision.recommended_mode}
          </span>
        </div>
        <div className="rounded bg-white/60 p-2 dark:bg-black/30">
          <span className="block text-[11px] text-gray-500 dark:text-gray-400">预估加速比</span>
          <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
            {decision.estimated_speedup_ratio}x 响应提速
          </span>
        </div>
        <div className="rounded bg-white/60 p-2 dark:bg-black/30">
          <span className="block text-[11px] text-gray-500 dark:text-gray-400">规避节省 Token</span>
          <span className="text-xs font-semibold text-indigo-600 dark:text-indigo-400">
            {decision.estimated_tokens_saved.toLocaleString()} Tokens
          </span>
        </div>
        <div className="rounded bg-white/60 p-2 dark:bg-black/30">
          <span className="block text-[11px] text-gray-500 dark:text-gray-400">独立并行数/深度</span>
          <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">
            {decision.features.independent_parallel_count} 分支 / {decision.features.max_dependency_depth} 阶
          </span>
        </div>
      </div>
    </section>
  );
};
