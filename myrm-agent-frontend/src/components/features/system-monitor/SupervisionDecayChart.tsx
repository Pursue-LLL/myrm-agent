import React from 'react';
import { SupervisionDecayPoint } from './types';

export interface SupervisionDecayChartProps {
  points: SupervisionDecayPoint[];
  className?: string;
}

export const SupervisionDecayChart: React.FC<SupervisionDecayChartProps> = ({
  points,
  className = '',
}) => {
  if (!points || points.length === 0) {
    return (
      <div
        className={`p-6 text-center text-xs text-gray-400 bg-gray-50/50 dark:bg-gray-800/30 rounded-lg border border-dashed border-gray-200 dark:border-gray-800 ${className}`}
        data-testid="supervision-decay-empty"
      >
        暂无重复场景监督衰减历史数据
      </div>
    );
  }

  const maxRate = Math.max(...points.map((p) => p.intervention_rate_pct), 100);

  return (
    <div
      className={`p-4 bg-gray-50/80 dark:bg-gray-800/40 rounded-xl border border-gray-200/80 dark:border-gray-800 space-y-3 ${className}`}
      data-testid="supervision-decay-chart"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-base">📉</span>
          <div>
            <h4 className="text-xs font-bold text-gray-900 dark:text-gray-100">
              重复场景人工监督衰减曲线 (Supervision Decay Curve)
            </h4>
            <p className="text-[11px] text-gray-500 dark:text-gray-400">
              随着执行经验沉淀与规约固化，人工盯梢介入率逐轮显著衰减
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-gray-500">
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-indigo-500" />
            <span>人工介入率 (%)</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            <span>关注时长 (分钟)</span>
          </span>
        </div>
      </div>

      {/* Bar / Ladder Series */}
      <div className="grid grid-cols-6 gap-2 pt-2 items-end min-h-[140px]">
        {points.map((p) => {
          const heightPct = Math.min(100, Math.max(10, (p.intervention_rate_pct / maxRate) * 100));
          return (
            <div
              key={p.sequence_number}
              className="flex flex-col items-center gap-1.5 h-full justify-end group"
              data-testid={`decay-step-${p.sequence_number}`}
            >
              {/* Values Tooltip */}
              <div className="text-[10px] font-mono text-gray-500 dark:text-gray-400 opacity-90 group-hover:scale-105 transition-transform text-center">
                <div className="font-bold text-indigo-600 dark:text-indigo-400">
                  {p.intervention_rate_pct.toFixed(0)}%
                </div>
                <div className="text-[9px] text-emerald-600 dark:text-emerald-400">
                  {p.average_attention_minutes.toFixed(0)}m
                </div>
              </div>

              {/* Progress Pillar */}
              <div className="w-full bg-gray-200 dark:bg-gray-700/60 rounded-t-md h-24 flex items-end p-1">
                <div
                  className="w-full bg-gradient-to-t from-indigo-600 to-indigo-400 dark:from-indigo-500 dark:to-indigo-300 rounded-t transition-all duration-500 group-hover:brightness-110"
                  style={{ height: `${heightPct}%` }}
                />
              </div>

              {/* Sequence Label */}
              <div className="text-[11px] font-medium text-gray-600 dark:text-gray-300">
                第 {p.sequence_number} 轮
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
