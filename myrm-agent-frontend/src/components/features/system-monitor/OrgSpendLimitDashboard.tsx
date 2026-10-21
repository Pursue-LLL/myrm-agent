/**
 * [INPUT]: OrgSpendSummary, IdentAttributionItem list, and pre-check actions.
 * [OUTPUT]: OrgSpendLimitDashboard component visualizing org budget watermarks, circuit breakers, and user attributions.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/OrgSpendLimitDashboard.tsx
 */

import React, { useState } from 'react';
import {
  GovernorAction,
  IdentAttributionItem,
  OrgSpendSummary,
  SpendGovernorDecision,
  SpendSurface,
} from './orgSpendLimitTypes';

export interface OrgSpendLimitDashboardProps {
  orgId: string;
  summary: OrgSpendSummary;
  attributions: IdentAttributionItem[];
  onPreCheck?: (surface: SpendSurface, estimatedCostUsd: number) => Promise<SpendGovernorDecision>;
  onRefresh?: () => void;
}

export const OrgSpendLimitDashboard: React.FC<OrgSpendLimitDashboardProps> = ({
  orgId,
  summary,
  attributions,
  onPreCheck,
  onRefresh,
}) => {
  const [testSurface, setTestSurface] = useState<SpendSurface>('CHANNEL');
  const [testCostUsd, setTestCostUsd] = useState<number>(0.5);
  const [simulatedDecision, setSimulatedDecision] = useState<SpendGovernorDecision | null>(null);
  const [isPrechecking, setIsPrechecking] = useState<boolean>(false);

  const isCircuitBreakerTripped = summary.utilization_pct >= 100.0;
  const isApproachingLimit = summary.utilization_pct >= 80.0 && !isCircuitBreakerTripped;

  const handleRunPreCheck = async () => {
    if (!onPreCheck) {
      // Local fallback simulation if no remote handler passed
      const nextSpend = summary.current_spend_usd + testCostUsd;
      const willTrip = testSurface === 'CHANNEL' && nextSpend >= summary.monthly_budget_usd;
      const willWarn = testSurface === 'CHANNEL' && (nextSpend / summary.monthly_budget_usd) >= 0.8;
      const action: GovernorAction = willTrip
        ? 'CIRCUIT_BREAKER_BLOCKED'
        : willWarn
        ? 'WARN_APPROACHING'
        : 'ALLOW';

      setSimulatedDecision({
        action,
        current_spend_usd: summary.current_spend_usd,
        monthly_budget_usd: summary.monthly_budget_usd,
        utilization_pct: Math.min(100, (summary.current_spend_usd / summary.monthly_budget_usd) * 100),
        reason: willTrip
          ? 'Monthly org budget exceeded. Shared channel execution halted.'
          : testSurface === 'DIRECT_MESSAGE'
          ? 'Bypassed org budget: Direct message billed to personal account.'
          : 'Budget capacity healthy.',
        is_blocked: willTrip,
      });
      return;
    }

    try {
      setIsPrechecking(true);
      const res = await onPreCheck(testSurface, testCostUsd);
      setSimulatedDecision(res);
    } finally {
      setIsPrechecking(false);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 text-slate-100 shadow-xl space-y-6">
      {/* 头部状态条 */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-bold text-sm">
            ORG-LIMIT
          </div>
          <div>
            <h2 className="text-base font-semibold text-white flex items-center gap-2">
              Org Shared Spend Governor
              <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-mono">
                {orgId}
              </span>
            </h2>
            <p className="text-xs text-slate-400">
              月度共享预算硬熔断门禁与 ident 身份标签算力归因透视
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="px-3 py-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-md transition-colors"
            >
              刷新数据
            </button>
          )}
          <div
            className={`px-2.5 py-1 rounded-md text-xs font-medium border ${
              isCircuitBreakerTripped
                ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                : isApproachingLimit
                ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
            }`}
          >
            {isCircuitBreakerTripped
              ? '● CIRCUIT BREAKER TRIPPED'
              : isApproachingLimit
              ? '▲ 80% WATERMARK WARNING'
              : '✔ BUDGET HEALTHY'}
          </div>
        </div>
      </div>

      {/* 熔断告警横幅 */}
      {isCircuitBreakerTripped && (
        <div className="p-4 rounded-lg bg-rose-950/40 border border-rose-800/60 text-rose-200 flex items-start gap-3">
          <div className="text-xl">🛑</div>
          <div className="text-xs space-y-1">
            <p className="font-semibold text-rose-300 text-sm">
              组织月度 Agent 算力共享预算已 100% 耗尽，硬熔断机制生效中！
            </p>
            <p className="text-slate-300">
              群组协同与公共自动化渠道（CHANNEL）已被阻断挂起，避免产生非预期超额账单。
              成员私信私聊（DIRECT_MESSAGE）自主承担计费通道保持正常放行。
            </p>
          </div>
        </div>
      )}

      {/* 预算仪表盘与水位进度条 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="p-4 rounded-lg bg-slate-800/40 border border-slate-700/50">
          <span className="text-xs text-slate-400">月度预算上限</span>
          <div className="text-xl font-bold text-white mt-1">
            ${summary.monthly_budget_usd.toFixed(2)}
          </div>
          <span className="text-[11px] text-slate-500">硬限额硬熔断阈值</span>
        </div>

        <div className="p-4 rounded-lg bg-slate-800/40 border border-slate-700/50">
          <span className="text-xs text-slate-400">当前累计支出</span>
          <div
            className={`text-xl font-bold mt-1 ${
              isCircuitBreakerTripped
                ? 'text-rose-400'
                : isApproachingLimit
                ? 'text-amber-400'
                : 'text-indigo-300'
            }`}
          >
            ${summary.current_spend_usd.toFixed(2)}
          </div>
          <span className="text-[11px] text-slate-500">本自然月度已入账总额</span>
        </div>

        <div className="p-4 rounded-lg bg-slate-800/40 border border-slate-700/50">
          <span className="text-xs text-slate-400">剩余可用额度</span>
          <div
            className={`text-xl font-bold mt-1 ${
              summary.remaining_budget_usd <= 0 ? 'text-rose-400' : 'text-emerald-400'
            }`}
          >
            ${summary.remaining_budget_usd.toFixed(2)}
          </div>
          <span className="text-[11px] text-slate-500">
            {summary.remaining_budget_usd <= 0 ? '额度耗尽' : '共享池充裕'}
          </span>
        </div>

        <div className="p-4 rounded-lg bg-slate-800/40 border border-slate-700/50">
          <span className="text-xs text-slate-400">预算水位使用率</span>
          <div className="text-xl font-bold text-white mt-1">
            {summary.utilization_pct.toFixed(1)}%
          </div>
          <span className="text-[11px] text-slate-500">
            共计 {summary.total_records_count} 笔调用上报
          </span>
        </div>
      </div>

      {/* 进度条可视化 */}
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs text-slate-400">
          <span>预算消耗进度</span>
          <span>{summary.utilization_pct.toFixed(1)}% / 100%</span>
        </div>
        <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden relative border border-slate-700">
          {/* 80% 软预警参考线 */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-amber-400/70 z-10"
            style={{ left: '80%' }}
            title="80% 软预警线"
          />
          <div
            className={`h-full transition-all duration-300 ${
              isCircuitBreakerTripped
                ? 'bg-rose-500'
                : isApproachingLimit
                ? 'bg-amber-500'
                : 'bg-indigo-500'
            }`}
            style={{ width: `${Math.min(100, Math.max(0, summary.utilization_pct))}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-slate-500 px-0.5">
          <span>0%</span>
          <span className="text-amber-400">80% 软预警</span>
          <span className="text-rose-400">100% 熔断阻断</span>
        </div>
      </div>

      {/* 用户身份标签 (ident:<id>) 归因消耗对账表 */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-200">
            成员身份归因对账排行 (ident:namespace)
          </h3>
          <span className="text-xs text-slate-400">共 {attributions.length} 位活跃发起者</span>
        </div>

        <div className="overflow-x-auto border border-slate-800 rounded-lg">
          <table className="w-full text-xs text-left text-slate-300">
            <thead className="bg-slate-800/60 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="px-3 py-2.5 font-medium">发起人身份 (ident)</th>
                <th className="px-3 py-2.5 font-medium">调用次数</th>
                <th className="px-3 py-2.5 font-medium">总消耗 Tokens</th>
                <th className="px-3 py-2.5 font-medium">累计金额 (USD)</th>
                <th className="px-3 py-2.5 font-medium">主要应用场景</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {attributions.length === 0 ? (
                <tr>
                  <td colSpan={5} className="text-center py-4 text-slate-500">
                    暂无消费记录归因
                  </td>
                </tr>
              ) : (
                attributions.map((item) => (
                  <tr key={item.requesting_user_id} className="hover:bg-slate-800/30">
                    <td className="px-3 py-2.5 font-mono text-indigo-300">
                      {item.requesting_user_id}
                    </td>
                    <td className="px-3 py-2.5">{item.total_calls_count} 次</td>
                    <td className="px-3 py-2.5 font-mono text-slate-400">
                      {item.total_tokens.toLocaleString()}
                    </td>
                    <td className="px-3 py-2.5 font-semibold text-emerald-400">
                      ${item.total_spend_usd.toFixed(4)}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 font-mono text-[11px]">
                        {item.primary_surface}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 智能体试算模拟预检测试台 */}
      <div className="p-4 rounded-lg bg-slate-800/30 border border-slate-800 space-y-3">
        <h3 className="text-xs font-semibold text-slate-300">
          智能体执行前快速预检试算台 (Pre-check Guard Simulator)
        </h3>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-400">发起场景:</label>
            <select
              value={testSurface}
              onChange={(e) => setTestSurface(e.target.value as SpendSurface)}
              className="bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-xs text-white"
            >
              <option value="CHANNEL">CHANNEL (群聊公摊)</option>
              <option value="DIRECT_MESSAGE">DIRECT_MESSAGE (私聊自费)</option>
              <option value="REST_API">REST_API (服务集成)</option>
              <option value="AUTOMATED_CI">AUTOMATED_CI (CI/CD)</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-400">预估费用 ($):</label>
            <input
              type="number"
              step="0.1"
              min="0"
              value={testCostUsd}
              onChange={(e) => setTestCostUsd(parseFloat(e.target.value) || 0)}
              className="w-20 bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white font-mono"
            />
          </div>

          <button
            onClick={handleRunPreCheck}
            disabled={isPrechecking}
            className="px-3 py-1 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded text-xs font-medium transition-colors"
          >
            {isPrechecking ? '预检计算中...' : '执行预检决策'}
          </button>
        </div>

        {simulatedDecision && (
          <div
            className={`p-3 rounded-md border text-xs flex items-center justify-between ${
              simulatedDecision.action === 'CIRCUIT_BREAKER_BLOCKED'
                ? 'bg-rose-950/30 border-rose-800 text-rose-300'
                : simulatedDecision.action === 'WARN_APPROACHING'
                ? 'bg-amber-950/30 border-amber-800 text-amber-300'
                : 'bg-emerald-950/30 border-emerald-800 text-emerald-300'
            }`}
          >
            <div className="flex items-center gap-2">
              <span className="font-bold">决策动作: {simulatedDecision.action}</span>
              <span>— {simulatedDecision.reason}</span>
            </div>
            <div className="font-mono">
              状态: {simulatedDecision.is_blocked ? '已阻断挂起' : '放行'}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
