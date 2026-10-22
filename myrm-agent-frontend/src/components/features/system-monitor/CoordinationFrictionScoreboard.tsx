import React from 'react';
import { CoordinationScoreboardSummary } from './types';
import { SupervisionDecayChart } from './SupervisionDecayChart';

export interface CoordinationFrictionScoreboardProps {
  summary: CoordinationScoreboardSummary;
  onSelectTemplate?: (template: string) => void;
  className?: string;
}

export const CoordinationFrictionScoreboard: React.FC<CoordinationFrictionScoreboardProps> = ({
  summary,
  onSelectTemplate,
  className = '',
}) => {
  const templates = summary.active_templates || [];

  return (
    <div
      className={`bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 shadow-sm space-y-5 text-gray-800 dark:text-gray-200 ${className}`}
      data-testid="coordination-friction-scoreboard"
    >
      {/* Top Header & Template Selector */}
      <div className="flex items-center justify-between border-b border-gray-100 dark:border-gray-800 pb-3">
        <div className="flex items-center gap-2">
          <span className="text-xl">🤝</span>
          <div>
            <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">
              人机协调摩擦度量与监督衰减记分板
            </h3>
            <p className="text-[11px] text-gray-400">
              破除多智能体技术虚荣，量化人机介入密度与真实注意力节省
            </p>
          </div>
        </div>

        {/* Template Selector */}
        {templates.length > 0 && (
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-400 font-medium">业务模板:</label>
            <select
              value={summary.template_type}
              onChange={(e) => onSelectTemplate?.(e.target.value)}
              className="text-xs py-1 px-2.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
              data-testid="template-selector"
            >
              <option value="global">全域汇总 (Global)</option>
              {templates.map((tmpl) => (
                <option key={tmpl} value={tmpl}>
                  {tmpl}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* 4 Core KPI Stat Cards */}
      <div className="grid grid-cols-4 gap-3">
        {/* Coordination Friction Density */}
        <div className="p-3.5 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-100 dark:border-gray-800">
          <div className="text-xs text-gray-500 dark:text-gray-400 font-medium">协调摩擦密度</div>
          <div className="text-lg font-extrabold text-indigo-600 dark:text-indigo-400 mt-1">
            {summary.average_friction_rate.toFixed(1)}{' '}
            <span className="text-xs font-normal text-gray-400">次 / 10步</span>
          </div>
          <div className="text-[11px] text-gray-400 mt-0.5">
            总执行轮次: <span className="font-semibold">{summary.total_runs} 轮</span>
          </div>
        </div>

        {/* Rework Rate */}
        <div className="p-3.5 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-100 dark:border-gray-800">
          <div className="text-xs text-gray-500 dark:text-gray-400 font-medium">打回重做率 (Rework)</div>
          <div
            className={`text-lg font-extrabold mt-1 ${
              summary.rework_rate_pct > 25 ? 'text-amber-500' : 'text-emerald-600 dark:text-emerald-400'
            }`}
          >
            {summary.rework_rate_pct.toFixed(1)}%
          </div>
          <div className="text-[11px] text-gray-400 mt-0.5">
            {summary.rework_rate_pct <= 20 ? '交付达标率高' : '需优化规划提示词'}
          </div>
        </div>

        {/* Net Hours Saved */}
        <div className="p-3.5 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-100 dark:border-gray-800">
          <div className="text-xs text-gray-500 dark:text-gray-400 font-medium">净节省协调时间</div>
          <div className="text-lg font-extrabold text-blue-600 dark:text-blue-400 mt-1">
            {summary.total_coordination_hours_saved.toFixed(1)}{' '}
            <span className="text-xs font-normal text-gray-400">小时</span>
          </div>
          <div className="text-[11px] text-gray-400 mt-0.5">负责人注意力直接挽回</div>
        </div>

        {/* Supervision Decay Reduction */}
        <div className="p-3.5 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-100 dark:border-gray-800">
          <div className="text-xs text-gray-500 dark:text-gray-400 font-medium">监督介入衰减度</div>
          <div className="text-lg font-extrabold text-emerald-600 dark:text-emerald-400 mt-1">
            {summary.friction_decay_pct.toFixed(1)}%
          </div>
          <div className="text-[11px] text-gray-400 mt-0.5">
            {summary.friction_decay_pct < -50 ? 'AI 熟练度显著飞跃' : '沉淀初期稳定中'}
          </div>
        </div>
      </div>

      {/* Supervision Decay Chart */}
      <SupervisionDecayChart points={summary.decay_curve} />

      {/* Tangible Business Outcomes Box */}
      <div className="p-3.5 bg-indigo-50/60 dark:bg-indigo-950/20 border border-indigo-200/80 dark:border-indigo-900/40 rounded-lg flex items-center justify-between text-xs">
        <div className="flex items-center gap-2 text-indigo-900 dark:text-indigo-200">
          <span className="text-base">💎</span>
          <span>
            <strong>真实业务成效验证：</strong>该业务产线已从最初的<strong>高频盯梢（100% 介入）</strong>平滑过渡至<strong>自主运转（仅特批介入）</strong>，负责人无需时刻紧绷盯屏。
          </span>
        </div>
        <span className="font-mono text-[10px] bg-indigo-100 dark:bg-indigo-900 px-2 py-0.5 rounded text-indigo-700 dark:text-indigo-300 shrink-0">
          ROI 标杆已确立
        </span>
      </div>
    </div>
  );
};
