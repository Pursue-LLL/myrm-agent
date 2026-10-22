/**
 * [INPUT]: RoleEngineeringInsightReport, active role filter, and role change callbacks.
 * [OUTPUT]: Engineering insight dashboard displaying 7-dimensional bottleneck signals, role-tailored perspectives (CTO/EM/FinOps/DevOps), and actionable remediations.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/EngineeringInsightRoleDeck.tsx
 */

import React from 'react';
import type {
  EngineeringSignalItem,
  RoleEngineeringInsightReport,
  RoleInsightView,
} from './contextSavingsTypes';

export interface EngineeringInsightRoleDeckProps {
  report: RoleEngineeringInsightReport;
  selectedRole: RoleInsightView;
  onRoleChange: (role: RoleInsightView) => void;
  onTriggerSessionScan?: () => void;
}

export const EngineeringInsightRoleDeck: React.FC<EngineeringInsightRoleDeckProps> = ({
  report,
  selectedRole,
  onRoleChange,
  onTriggerSessionScan,
}) => {
  const roles: RoleInsightView[] = ['CTO', 'EM', 'FINOPS', 'DEVOPS'];

  const getSeverityBadgeClass = (severity: string) => {
    switch (severity.toUpperCase()) {
      case 'HIGH':
        return 'bg-rose-950/80 text-rose-300 border-rose-700';
      case 'MEDIUM':
        return 'bg-amber-950/80 text-amber-300 border-amber-700';
      default:
        return 'bg-cyan-950/80 text-cyan-300 border-cyan-700';
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-5 text-slate-100">
      {/* Header & Role Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl">📊</span>
            <h2 className="text-base font-semibold text-white">跨工具 Token 节省率与工程信号七维决策看板</h2>
            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-950 text-indigo-300 border border-indigo-700/60">
              Context Mode Insight
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            结构化元数据分析 · 7 维研发阻碍模式识别 · CTO / EM / FinOps / DevOps 多角色决策视窗
          </p>
        </div>

        {/* Role Tabs */}
        <div className="flex items-center bg-slate-850 p-1 rounded-lg border border-slate-750">
          {roles.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => onRoleChange(r)}
              className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${
                selectedRole === r
                  ? 'bg-cyan-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      {/* Primary Bottleneck Banner */}
      <div className="p-3.5 rounded-lg bg-slate-850/80 border border-slate-750 flex items-center justify-between gap-3">
        <div className="text-xs text-slate-300 flex items-center gap-2">
          <span className="text-cyan-400 font-semibold">【{report.role} 视角聚焦】</span>
          <span>{report.primary_bottleneck_summary}</span>
        </div>
        {onTriggerSessionScan && (
          <button
            type="button"
            onClick={onTriggerSessionScan}
            className="px-2.5 py-1 text-[11px] font-medium rounded bg-slate-800 hover:bg-slate-700 text-cyan-300 border border-slate-700 transition-colors whitespace-nowrap"
          >
            🔄 重新扫描信号
          </button>
        )}
      </div>

      {/* Aggregate KPI Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
        <div className="p-3.5 rounded-lg bg-slate-800/50 border border-slate-750">
          <div className="text-[11px] font-medium text-slate-400">评估会话总量</div>
          <div className="mt-1 flex items-baseline gap-1.5">
            <span className="text-xl font-bold font-mono text-white">
              {report.evaluated_sessions_count}
            </span>
            <span className="text-xs text-slate-500">场会话</span>
          </div>
        </div>

        <div className="p-3.5 rounded-lg bg-slate-800/50 border border-slate-750">
          <div className="text-[11px] font-medium text-slate-400">组织累计节省 Token</div>
          <div className="mt-1 flex items-baseline gap-1.5">
            <span className="text-xl font-bold font-mono text-emerald-400">
              {report.total_saved_tokens_aggregate.toLocaleString()}
            </span>
            <span className="text-xs text-slate-500">Tokens</span>
          </div>
        </div>

        <div className="p-3.5 rounded-lg bg-slate-800/50 border border-slate-750">
          <div className="text-[11px] font-medium text-slate-400">折合挽回财务预算</div>
          <div className="mt-1 flex items-baseline gap-1.5">
            <span className="text-xl font-bold font-mono text-amber-400">
              ${report.total_cost_saved_usd_aggregate.toFixed(2)}
            </span>
            <span className="text-xs text-slate-500">USD</span>
          </div>
        </div>

        <div className="p-3.5 rounded-lg bg-slate-800/50 border border-slate-750">
          <div className="text-[11px] font-medium text-slate-400">最高效提效工具</div>
          <div className="mt-1 text-xs font-mono text-cyan-300 truncate">
            {report.top_efficiency_tools.length > 0
              ? report.top_efficiency_tools.join(', ')
              : '暂无'}
          </div>
        </div>
      </div>

      {/* Engineering Signals List */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            工程障碍模式检测信号 ({report.identified_engineering_signals.length})
          </h3>
          <span className="text-[11px] text-slate-500">覆盖输出膨胀 / 重试死循环 / 阻塞I/O / 缓存饥渴</span>
        </div>

        {report.identified_engineering_signals.length === 0 ? (
          <div className="p-6 text-center text-slate-500 bg-slate-850/40 rounded-lg border border-dashed border-slate-800 text-xs">
            🎉 当前视角下未发现严重工程阻塞模式，流水线效能健康！
          </div>
        ) : (
          <div className="space-y-2.5">
            {report.identified_engineering_signals.map((sig, idx) => (
              <div
                key={`${sig.signal_pattern}-${sig.target_entity}-${idx}`}
                className="p-3.5 rounded-lg bg-slate-850/60 border border-slate-800 hover:border-slate-700 transition-all space-y-2"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold border ${getSeverityBadgeClass(
                        sig.severity
                      )}`}
                    >
                      {sig.severity}
                    </span>
                    <span className="font-mono text-xs font-semibold text-slate-200">
                      {sig.signal_pattern}
                    </span>
                    <span className="text-xs text-slate-400 font-mono">
                      (目标: <code className="text-cyan-400">{sig.target_entity}</code>)
                    </span>
                  </div>
                  <span className="text-[11px] text-slate-400 font-mono">
                    实测值: {sig.detected_metric_value.toLocaleString()} / 门禁: {sig.metric_threshold.toLocaleString()}
                  </span>
                </div>

                <div className="text-xs text-slate-300 leading-relaxed">
                  <span className="text-slate-400">根因分析: </span>
                  {sig.root_cause_explanation}
                </div>

                <div className="text-xs text-cyan-300/90 pt-1 border-t border-slate-800 flex items-start gap-1.5">
                  <span className="text-cyan-400">💡 推荐行动:</span>
                  <span>{sig.actionable_remediation}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
