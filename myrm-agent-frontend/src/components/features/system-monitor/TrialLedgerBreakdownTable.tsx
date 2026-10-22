/**
 * [INPUT]
 * - trials: TrialRecordItem[] 单次 Worker 尝试明细列表
 *
 * [OUTPUT]
 * - TrialLedgerBreakdownTable: 单次尝试流水明细表组件
 *
 * [POS]
 * src/components/features/system-monitor/TrialLedgerBreakdownTable.tsx — 单次 Worker 尝试流水与未知用量计提明细表
 */

import React from 'react';
import type { TrialRecordItem } from './deliveryBudgetTypes';

export interface TrialLedgerBreakdownTableProps {
  trials: TrialRecordItem[];
  className?: string;
}

export const TrialLedgerBreakdownTable: React.FC<TrialLedgerBreakdownTableProps> = ({
  trials,
  className = '',
}) => {
  if (trials.length === 0) {
    return (
      <div
        data-testid="trial-breakdown-empty"
        className="p-4 text-center text-xs text-slate-500 bg-slate-900/60 rounded-lg border border-slate-800"
      >
        暂无单次尝试记录
      </div>
    );
  }

  return (
    <div
      data-testid="trial-breakdown-table-container"
      className={`overflow-x-auto rounded-lg border border-slate-800 bg-slate-950/60 ${className}`}
    >
      <table className="w-full text-left border-collapse text-xs">
        <thead>
          <tr className="border-b border-slate-800 bg-slate-900/80 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            <th className="py-2.5 px-3">轮次 / 角色</th>
            <th className="py-2.5 px-3">步骤说明</th>
            <th className="py-2.5 px-3">计量状态</th>
            <th className="py-2.5 px-3 text-right">有效 Token</th>
            <th className="py-2.5 px-3 text-right">费用 ($)</th>
            <th className="py-2.5 px-3 text-right">耗时</th>
            <th className="py-2.5 px-3 text-center">状态</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/60 text-slate-300">
          {trials.map((trial) => (
            <tr
              key={trial.trial_id}
              data-testid={`trial-row-${trial.trial_id}`}
              className={`hover:bg-slate-900/50 transition-colors ${
                trial.is_unmetered ? 'bg-amber-950/15' : ''
              }`}
            >
              {/* 轮次与角色 */}
              <td className="py-2.5 px-3">
                <div className="flex items-center space-x-1.5">
                  <span className="font-mono text-slate-400 font-medium">#{trial.attempt_index}</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-indigo-300 border border-slate-700/60">
                    {trial.agent_role}
                  </span>
                </div>
                <div className="text-[10px] font-mono text-slate-500 mt-0.5">{trial.agent_id}</div>
              </td>

              {/* 步骤说明 */}
              <td className="py-2.5 px-3">
                <div className="font-medium text-slate-200">{trial.step_name}</div>
                <div className="text-[10px] text-slate-500 font-mono">{trial.trial_id}</div>
              </td>

              {/* 计量状态 */}
              <td className="py-2.5 px-3">
                {trial.is_unmetered ? (
                  <div className="space-y-0.5">
                    <span
                      data-testid={`unmetered-badge-${trial.trial_id}`}
                      className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-950/60 text-amber-300 border border-amber-800/80"
                    >
                      ⚠️ 未知用量保守计提
                    </span>
                    <div className="text-[10px] text-amber-400/80 font-mono">
                      {trial.unmetered_status} (+{trial.imputed_prompt_tokens + trial.imputed_completion_tokens} T)
                    </div>
                  </div>
                ) : (
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-950/40 text-emerald-300 border border-emerald-800/60">
                    精确计量
                  </span>
                )}
              </td>

              {/* 有效 Token */}
              <td className="py-2.5 px-3 text-right font-mono">
                <span className={trial.is_unmetered ? 'text-amber-300 font-semibold' : 'text-slate-200'}>
                  {trial.effective_tokens.toLocaleString()}
                </span>
                {trial.is_unmetered && (
                  <span className="text-[10px] text-amber-400/80 ml-1">(计提)</span>
                )}
              </td>

              {/* 费用 */}
              <td className="py-2.5 px-3 text-right font-mono text-slate-300">
                ${trial.effective_cost_usd.toFixed(4)}
              </td>

              {/* 耗时 */}
              <td className="py-2.5 px-3 text-right font-mono text-slate-400">
                {(trial.latency_ms / 1000).toFixed(1)}s
              </td>

              {/* 状态 */}
              <td className="py-2.5 px-3 text-center">
                <span
                  className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${
                    trial.status === 'success'
                      ? 'bg-emerald-950/30 text-emerald-400'
                      : 'bg-rose-950/40 text-rose-300'
                  }`}
                >
                  {trial.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
