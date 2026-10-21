/**
 * [INPUT]: isOpen, onClose, alert (CostDriftAlert).
 * [OUTPUT]: Sliding drawer revealing historical unit-cost baseline drift, percentage surge, and root-cause attribution.
 * [POS]: myrm-agent-frontend/src/components/features/system-monitor/CostDriftExplainerDrawer.tsx
 */

import React from 'react';
import { CostDriftAlert, DriftReasonType } from './tokenEconomicsTypes';

export interface CostDriftExplainerDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  alert: CostDriftAlert | null;
}

const REASON_LABELS: Record<DriftReasonType, { title: string; badgeColor: string }> = {
  NORMAL: {
    title: '基线平稳',
    badgeColor: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800',
  },
  CACHE_HIT_DEGRADED: {
    title: '缓存击穿劣化',
    badgeColor: 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 border-amber-200 dark:border-amber-800',
  },
  ROUTING_FALLBACK: {
    title: '模型降级路由',
    badgeColor: 'bg-orange-50 text-orange-700 dark:bg-orange-950/40 dark:text-orange-300 border-orange-200 dark:border-orange-800',
  },
  UPSTREAM_PRICE_INCREASE: {
    title: '上游单价上调',
    badgeColor: 'bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300 border-red-200 dark:border-red-800',
  },
  SUBSIDY_REVOKED: {
    title: '补贴额度撤销',
    badgeColor: 'bg-purple-50 text-purple-700 dark:bg-purple-950/40 dark:text-purple-300 border-purple-200 dark:border-purple-800',
  },
  PROMPT_BLOAT: {
    title: '单轮上下文剧烈膨胀',
    badgeColor: 'bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300 border-blue-200 dark:border-blue-800',
  },
};

export const CostDriftExplainerDrawer: React.FC<CostDriftExplainerDrawerProps> = ({
  isOpen,
  onClose,
  alert,
}) => {
  if (!isOpen || !alert) return null;

  const reasonConfig = REASON_LABELS[alert.reason] || REASON_LABELS.NORMAL;

  return (
    <div
      className="fixed inset-0 z-50 overflow-hidden bg-black/40 backdrop-blur-sm flex justify-end"
      data-testid="cost-drift-drawer"
    >
      <div className="w-full max-w-md bg-white dark:bg-gray-900 border-l border-gray-200 dark:border-gray-800 h-full flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 dark:border-gray-800">
          <div className="flex items-center gap-2">
            <span className="text-xl">📈</span>
            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                周期单位成本漂移感知
              </h3>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                跨任务相对基线检测 · 拒绝静默变贵
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 p-1 rounded-lg"
            data-testid="drawer-close-btn"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6 flex-1 overflow-y-auto text-xs">
          {/* Category & Model Pill */}
          <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-100 dark:border-gray-800">
            <div>
              <div className="text-[10px] text-gray-400 uppercase">任务分类</div>
              <div className="font-semibold text-gray-800 dark:text-gray-200 mt-0.5" data-testid="drift-category">
                {alert.task_category}
              </div>
            </div>
            <div className="text-right">
              <div className="text-[10px] text-gray-400 uppercase">调用模型</div>
              <div className="font-mono text-gray-800 dark:text-gray-200 mt-0.5" data-testid="drift-model">
                {alert.model_name}
              </div>
            </div>
          </div>

          {/* Metrics comparison card */}
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 bg-blue-50/50 dark:bg-blue-950/20 border border-blue-100 dark:border-blue-900/40 rounded-lg">
              <div className="text-gray-500 dark:text-gray-400 text-[11px]">当前单位成本</div>
              <div className="text-lg font-bold text-blue-600 dark:text-blue-400 mt-1" data-testid="current-unit-cost">
                ¥{alert.current_unit_cost_per_k.toFixed(4)}
              </div>
              <div className="text-[10px] text-gray-400">每 1,000 Tokens</div>
            </div>
            <div className="p-3 bg-gray-50 dark:bg-gray-800/40 border border-gray-100 dark:border-gray-800 rounded-lg">
              <div className="text-gray-500 dark:text-gray-400 text-[11px]">历史滑动基线</div>
              <div className="text-lg font-bold text-gray-700 dark:text-gray-300 mt-1" data-testid="baseline-unit-cost">
                ¥{alert.baseline_unit_cost_per_k.toFixed(4)}
              </div>
              <div className="text-[10px] text-gray-400">过去 30 次任务均值</div>
            </div>
          </div>

          {/* Drift Status Banner */}
          <div className="p-4 border rounded-lg space-y-2 bg-gray-50/80 dark:bg-gray-800/40 border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between">
              <span className="text-gray-600 dark:text-gray-300 font-medium">相对漂移幅度:</span>
              <span
                className={`font-bold px-2 py-0.5 rounded text-xs ${
                  alert.drift_percentage > 20
                    ? 'bg-red-100 text-red-700 dark:bg-red-950/60 dark:text-red-300'
                    : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'
                }`}
                data-testid="drift-percentage"
              >
                {alert.drift_percentage > 0 ? `+${alert.drift_percentage}%` : `${alert.drift_percentage}%`}
              </span>
            </div>
            <div className="flex items-center gap-2 pt-1">
              <span className="text-gray-500">归因判定:</span>
              <span
                className={`px-2 py-0.5 text-[11px] font-semibold border rounded ${reasonConfig.badgeColor}`}
                data-testid="drift-reason-badge"
              >
                {reasonConfig.title}
              </span>
            </div>
          </div>

          {/* Detailed explanation */}
          <div className="space-y-1.5">
            <h4 className="font-semibold text-gray-900 dark:text-gray-100">透明度归因说明</h4>
            <p className="text-gray-600 dark:text-gray-300 leading-relaxed bg-gray-50 dark:bg-gray-800 p-3 rounded-lg border border-gray-100 dark:border-gray-700/60" data-testid="drift-explanation">
              {alert.explanation}
            </p>
          </div>

          {/* Actionable recommendations */}
          <div className="space-y-2 border-t border-gray-100 dark:border-gray-800 pt-4">
            <h4 className="font-semibold text-gray-900 dark:text-gray-100">建议优化策略</h4>
            <ul className="list-disc pl-4 space-y-1 text-gray-500 dark:text-gray-400 text-[11px]">
              <li>若缓存击穿：建议使用固定结构系统前缀并保证长会话首部稳定，利用 99% Prompt Cache 特性；</li>
              <li>若模型降级：在模型路由配置中锁定主力模型，避免静默回退；</li>
              <li>若单轮膨胀：适时执行上下文摘要压缩，减少无意义的全量文件刷屏。</li>
            </ul>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-100 dark:border-gray-800 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 dark:bg-gray-700 dark:hover:bg-gray-600 text-white rounded-lg text-xs font-medium transition-colors"
          >
            知道了
          </button>
        </div>
      </div>
    </div>
  );
};
