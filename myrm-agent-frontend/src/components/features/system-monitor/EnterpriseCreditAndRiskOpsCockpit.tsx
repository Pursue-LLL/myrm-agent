/**
 * [INPUT]: EnterpriseCreditAndRiskOpsCockpitProps containing cockpitData, quota handlers, and refresh.
 * [OUTPUT]: EnterpriseCreditAndRiskOpsCockpit React component visualizing unified credit pools and actor-time-data-risk audit chains.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/EnterpriseCreditAndRiskOpsCockpit.tsx
 */

import React, { useState } from 'react';
import {
  CreditPoolAllocationItem,
  CreditRiskAuditRecordItem,
  EnterpriseCreditAndRiskOpsCockpitProps,
  RiskLevelType,
} from './enterpriseCreditCockpitTypes';

export const EnterpriseCreditAndRiskOpsCockpit: React.FC<
  EnterpriseCreditAndRiskOpsCockpitProps
> = ({ cockpitData, onRefresh, onConfigureQuota, onReset, isRefreshing = false }) => {
  const [riskFilter, setRiskFilter] = useState<string>('ALL');
  const [showQuotaModal, setShowQuotaModal] = useState<boolean>(false);
  const [quotaInput, setQuotaInput] = useState<string>(
    String(cockpitData.total_credit_quota || 100000)
  );
  const [thresholdInput, setThresholdInput] = useState<string>(
    String(cockpitData.warning_threshold_pct || 80)
  );
  const [isSubmittingQuota, setIsSubmittingQuota] = useState<boolean>(false);

  const filteredRecords = (cockpitData.recent_audit_records || []).filter(
    (record: CreditRiskAuditRecordItem) => {
      if (riskFilter === 'ALL') return true;
      if (riskFilter === 'RISK_ONLY') return record.risk_level !== 'NONE';
      return record.risk_level === riskFilter;
    }
  );

  const handleSaveQuota = async (e?: React.FormEvent | React.MouseEvent) => {
    if (e && 'preventDefault' in e) {
      e.preventDefault();
    }
    if (!onConfigureQuota) return;
    const newQuota = parseFloat(quotaInput);
    const newThreshold = parseFloat(thresholdInput);
    if (isNaN(newQuota) || newQuota <= 0) return;
    setIsSubmittingQuota(true);
    try {
      await onConfigureQuota(newQuota, isNaN(newThreshold) ? 80 : newThreshold);
      setShowQuotaModal(false);
    } finally {
      setIsSubmittingQuota(false);
    }
  };

  const getRiskBadgeClass = (level: RiskLevelType) => {
    switch (level) {
      case 'CRITICAL':
        return 'border-rose-500/40 bg-rose-500/20 text-rose-400';
      case 'HIGH':
        return 'border-orange-500/40 bg-orange-500/20 text-orange-400';
      case 'MEDIUM':
        return 'border-amber-500/40 bg-amber-500/20 text-amber-300';
      case 'LOW':
        return 'border-sky-500/40 bg-sky-500/20 text-sky-300';
      default:
        return 'border-zinc-700 bg-zinc-800 text-zinc-400';
    }
  };

  const getVerdictBadgeClass = (verdict: string) => {
    switch (verdict) {
      case 'BLOCKED':
        return 'border-rose-600 bg-rose-950/60 text-rose-300';
      case 'AUDIT':
        return 'border-amber-600 bg-amber-950/60 text-amber-300';
      default:
        return 'border-emerald-600 bg-emerald-950/60 text-emerald-300';
    }
  };

  return (
    <div className="flex flex-col space-y-6 rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-xl">
      {/* 头部标题与控制栏 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center space-x-3">
            <span className="text-xl font-bold tracking-tight text-white">
              企业用量与风险运营驾驶舱 (Enterprise Credit & Risk Cockpit)
            </span>
            <span className="rounded-md border border-indigo-500/30 bg-indigo-500/10 px-2.5 py-0.5 font-mono text-xs font-medium text-indigo-400">
              人·时·数·险同链路
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            统一 Credit 池跨端治理，终结 Token 账单与安全风控割裂，穿透审计人员、时序、数据对象与处置决策
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            type="button"
            onClick={() => setShowQuotaModal(true)}
            className="inline-flex items-center rounded-lg border border-indigo-700 bg-indigo-950/40 px-3 py-1.5 text-xs font-medium text-indigo-300 transition-colors hover:bg-indigo-900/50"
          >
            调整企业配额
          </button>

          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={isRefreshing}
              className="inline-flex items-center rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-200 transition-colors hover:bg-zinc-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            >
              {isRefreshing ? '刷新中...' : '刷新大盘'}
            </button>
          )}

          {onReset && (
            <button
              type="button"
              onClick={onReset}
              className="inline-flex items-center rounded-lg border border-zinc-800 bg-zinc-900/80 px-2.5 py-1.5 text-xs text-zinc-400 hover:text-zinc-200"
            >
              重置
            </button>
          )}
        </div>
      </div>

      {/* 4 大核心 KPI 指标卡片 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/60 p-4">
          <span className="text-xs font-medium text-zinc-400">企业总 Credit 配额 (Quota)</span>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="font-mono text-2xl font-bold text-white">
              {cockpitData.total_credit_quota.toLocaleString()}
            </span>
            <span className="text-xs text-zinc-500">点数 (Credits)</span>
          </div>
        </div>

        <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/60 p-4">
          <span className="text-xs font-medium text-amber-400">已消耗点数与水位 (Spent)</span>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="font-mono text-2xl font-bold text-amber-300">
              {cockpitData.total_credit_spent.toLocaleString()}
            </span>
            <span className="font-mono text-xs text-amber-400">
              {cockpitData.utilization_pct}%
            </span>
          </div>
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
            <div
              className={`h-full transition-all duration-300 ${
                cockpitData.is_quota_breached
                  ? 'bg-rose-500'
                  : cockpitData.utilization_pct >= cockpitData.warning_threshold_pct
                  ? 'bg-amber-500'
                  : 'bg-indigo-500'
              }`}
              style={{ width: `${Math.min(100, cockpitData.utilization_pct)}%` }}
            />
          </div>
        </div>

        <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/60 p-4">
          <span className="text-xs font-medium text-emerald-400">可用剩余点数 (Available)</span>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="font-mono text-2xl font-bold text-emerald-300">
              {cockpitData.available_credit.toLocaleString()}
            </span>
            <span
              className={`text-xs ${
                cockpitData.is_quota_breached ? 'font-bold text-rose-400' : 'text-emerald-500'
              }`}
            >
              {cockpitData.is_quota_breached ? '⚠️ 额度耗尽熔断' : '安全余量'}
            </span>
          </div>
        </div>

        <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/60 p-4">
          <span className="text-xs font-medium text-rose-400">风险拦截统计 (Risk Ops)</span>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="font-mono text-2xl font-bold text-rose-300">
              {cockpitData.blocked_count}
            </span>
            <span className="text-xs text-zinc-400">
              风险事件: {cockpitData.risk_event_count} 起
            </span>
          </div>
        </div>
      </div>

      {/* 跨端 Credit 水位分布 */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
        <span className="text-xs font-semibold text-zinc-300">各产品端 Credit 分布 (Surface Allocation)</span>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {(cockpitData.allocations_by_surface || []).map((alloc: CreditPoolAllocationItem) => (
            <div
              key={alloc.surface_name}
              className="rounded-md border border-zinc-800/60 bg-zinc-950/70 p-3 text-xs"
            >
              <span className="font-mono uppercase text-zinc-400">{alloc.surface_name}</span>
              <div className="mt-1 flex items-baseline justify-between font-mono">
                <span className="text-base font-bold text-white">{alloc.credit_spent} 点</span>
                <span className="text-[11px] text-zinc-500">{alloc.request_count} 次</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 人·时·数·险同链路审计穿透面板 */}
      <div className="flex flex-col space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800 pb-3">
          <div className="flex items-center space-x-2">
            <span className="text-sm font-semibold text-white">
              人-时-数-险同链路审计流水 (Unified Audit Trail)
            </span>
            <span className="rounded bg-zinc-800 px-2 py-0.5 font-mono text-[11px] text-zinc-400">
              共 {cockpitData.total_audit_records} 条
            </span>
          </div>

          {/* 风险等级过滤器 */}
          <div className="flex items-center space-x-1.5 text-xs">
            <span className="text-zinc-500">过滤:</span>
            {['ALL', 'RISK_ONLY', 'CRITICAL', 'HIGH', 'NONE'].map((lvl) => (
              <button
                key={lvl}
                type="button"
                onClick={() => setRiskFilter(lvl)}
                className={`rounded px-2 py-0.5 font-mono text-[11px] transition-colors ${
                  riskFilter === lvl
                    ? 'bg-zinc-700 font-bold text-white'
                    : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200'
                }`}
              >
                {lvl}
              </button>
            ))}
          </div>
        </div>

        {/* 审计记录数据表 */}
        <div className="max-h-72 overflow-x-auto overflow-y-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-zinc-800/80 text-[11px] text-zinc-500">
                <th className="pb-2 font-medium">人员身份 (Actor)</th>
                <th className="pb-2 font-medium">产品端</th>
                <th className="pb-2 font-medium">交互摘要</th>
                <th className="pb-2 font-medium">访问数据对象 (Scope)</th>
                <th className="pb-2 font-medium">消耗</th>
                <th className="pb-2 font-medium">风险行为与等级</th>
                <th className="pb-2 font-medium">处置决策</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/40">
              {filteredRecords.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-zinc-500">
                    暂无符合条件的审计记录
                  </td>
                </tr>
              ) : (
                filteredRecords.map((rec: CreditRiskAuditRecordItem) => (
                  <tr key={rec.record_id} className="hover:bg-zinc-900/40">
                    <td className="py-2.5 font-mono font-semibold text-zinc-200">{rec.actor_id}</td>
                    <td className="py-2.5 font-mono text-zinc-400">{rec.product_surface}</td>
                    <td className="max-w-[180px] truncate py-2.5 text-zinc-300" title={rec.interaction_summary}>
                      {rec.interaction_summary}
                    </td>
                    <td className="py-2.5 font-mono text-indigo-300">{rec.data_object_scope}</td>
                    <td className="py-2.5 font-mono text-amber-300">{rec.credit_consumed} 点</td>
                    <td className="py-2.5">
                      <span
                        className={`inline-block rounded border px-1.5 py-0.5 font-mono text-[10px] font-bold ${getRiskBadgeClass(
                          rec.risk_level
                        )}`}
                      >
                        {rec.risk_level} · {rec.risk_behavior}
                      </span>
                    </td>
                    <td className="py-2.5">
                      <span
                        className={`inline-block rounded border px-2 py-0.5 font-mono text-[10px] font-bold ${getVerdictBadgeClass(
                          rec.policy_verdict
                        )}`}
                      >
                        {rec.policy_verdict}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 调整配额模态框 */}
      {showQuotaModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-sm rounded-xl border border-zinc-800 bg-zinc-900 p-5 shadow-2xl">
            <h3 className="text-sm font-bold text-white">调整企业 Credit 配额</h3>
            <p className="mt-1 text-xs text-zinc-400">
              修改企业 Credit 池上限及软警告阈值，超过上限将触发熔断。
            </p>
            <form onSubmit={handleSaveQuota} className="mt-4 space-y-3">
              <div>
                <label className="text-xs text-zinc-400">总 Credit 配额点数</label>
                <input
                  type="number"
                  min="1"
                  step="100"
                  value={quotaInput}
                  onChange={(e) => setQuotaInput(e.target.value)}
                  className="mt-1 w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-1.5 font-mono text-xs text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  required
                />
              </div>
              <div>
                <label className="text-xs text-zinc-400">警告阈值 (%)</label>
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={thresholdInput}
                  onChange={(e) => setThresholdInput(e.target.value)}
                  className="mt-1 w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-1.5 font-mono text-xs text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  required
                />
              </div>
              <div className="mt-4 flex justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowQuotaModal(false)}
                  className="rounded px-3 py-1.5 text-xs text-zinc-400 hover:text-white"
                >
                  取消
                </button>
                <button
                  type="submit"
                  onClick={handleSaveQuota}
                  disabled={isSubmittingQuota}
                  className="rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                >
                  {isSubmittingQuota ? '保存中...' : '确认更新'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
