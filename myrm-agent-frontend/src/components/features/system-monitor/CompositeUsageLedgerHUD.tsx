/**
 * [INPUT]: CompositeUsageLedgerHUDProps containing summary metrics, ledger records, and control handlers.
 * [OUTPUT]: CompositeUsageLedgerHUD React component visualizing 6D composite ledger, dual-track reconciliation, and task attributions.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/CompositeUsageLedgerHUD.tsx
 */

import React, { useState } from 'react';
import {
  CompositeUsageLedgerHUDProps,
  CompositeUsageRecordItem,
  CostReconciliationStatusType,
} from './compositeUsageLedgerTypes';

export const CompositeUsageLedgerHUD: React.FC<CompositeUsageLedgerHUDProps> = ({
  summary,
  records = [],
  onRefresh,
  onReconcile,
  onReset,
  isRefreshing = false,
}) => {
  const [selectedTaskFilter, setSelectedTaskFilter] = useState<string>('ALL');

  const filteredRecords = records.filter((r) => {
    if (selectedTaskFilter === 'ALL') return true;
    return r.task === selectedTaskFilter;
  });

  const getStatusBadge = (status: CostReconciliationStatusType, driftPct: number) => {
    switch (status) {
      case 'RECONCILED':
        return {
          text: `已对账 (偏差 ${driftPct.toFixed(1)}%)`,
          cls: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400',
        };
      case 'DISCREPANCY_ALERT':
        return {
          text: `⚠️ 偏差告警 (偏差 ${driftPct.toFixed(1)}%)`,
          cls: 'border-rose-500/40 bg-rose-500/10 text-rose-400',
        };
      case 'ESTIMATED_ONLY':
      default:
        return {
          text: '仅本地估算 (待对账)',
          cls: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
        };
    }
  };

  const uniqueTasks = Array.from(new Set(records.map((r) => r.task)));

  return (
    <div className="flex flex-col space-y-6 rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-xl">
      {/* 头部标题与控制栏 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center space-x-3">
            <span className="text-xl font-bold tracking-tight text-white">
              六维复合主键用量分摊账本与双轨对账 HUD
            </span>
            <span className="rounded-md border border-indigo-500/30 bg-indigo-500/10 px-2.5 py-0.5 text-xs font-semibold text-indigo-300">
              Hermes 风格持久账本
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            主键: (session_id, model, provider, base_url, mode, task) · 本地公开价估算与供应商实际扣费双轨核算
          </p>
        </div>

        <div className="flex items-center space-x-2">
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={isRefreshing}
              className="inline-flex items-center rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-200 transition-colors hover:bg-zinc-700 disabled:opacity-50"
            >
              {isRefreshing ? '刷新中...' : '刷新账本'}
            </button>
          )}

          {onReset && (
            <button
              type="button"
              onClick={onReset}
              className="inline-flex items-center rounded-lg border border-rose-900/50 bg-rose-950/40 px-3 py-1.5 text-xs font-medium text-rose-300 transition-colors hover:bg-rose-900/60"
            >
              清空账本
            </button>
          )}
        </div>
      </div>

      {/* 核心 KPI 卡片 4 大概览 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="text-xs font-medium text-zinc-400">估算总成本 (本地标尺)</div>
          <div className="mt-2 text-2xl font-bold text-white tracking-tight font-mono">
            ${summary.total_estimated_usd.toFixed(4)}
          </div>
          <div className="mt-1 text-[11px] text-zinc-500">官方公开价目表推导出的基线</div>
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="text-xs font-medium text-zinc-400">实际扣费总计 (发票回执)</div>
          <div className="mt-2 text-2xl font-bold text-emerald-400 tracking-tight font-mono">
            ${summary.total_actual_usd.toFixed(4)}
          </div>
          <div className="mt-1 text-[11px] text-zinc-500">外部聚合网关回传的真实扣费</div>
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-zinc-400">对账态势分布</span>
            {summary.discrepancy_records_count > 0 && (
              <span className="rounded border border-rose-500/40 bg-rose-500/10 px-1.5 py-0.2 text-[10px] text-rose-400">
                {summary.discrepancy_records_count} 笔超差
              </span>
            )}
          </div>
          <div className="mt-2 text-2xl font-bold text-indigo-300 tracking-tight">
            {summary.reconciled_records_count} / {summary.total_records}
          </div>
          <div className="mt-1 text-[11px] text-zinc-500">经核验偏差 &le; 15% 的记录数</div>
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="text-xs font-medium text-zinc-400">总调用与 Token 吞吐</div>
          <div className="mt-2 text-2xl font-bold text-amber-300 tracking-tight">
            {summary.total_calls.toLocaleString()} 次
          </div>
          <div className="mt-1 text-[11px] text-zinc-500">
            入: {(summary.total_input_tokens / 1000).toFixed(1)}k · 出: {(summary.total_output_tokens / 1000).toFixed(1)}k
          </div>
        </div>
      </div>

      {/* 细粒度任务维度归因与模型分摊 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
          <h3 className="text-sm font-semibold text-zinc-200 border-b border-zinc-800/80 pb-2">
            🎯 细粒度任务归因 (Task-Dimension Attribution)
          </h3>
          <div className="mt-3 space-y-2.5">
            {Object.keys(summary.task_spend_distribution).length === 0 ? (
              <div className="py-4 text-center text-xs text-zinc-500">暂无任务分摊记录</div>
            ) : (
              Object.entries(summary.task_spend_distribution).map(([taskName, spend]) => {
                const total = summary.total_actual_usd || summary.total_estimated_usd || 1;
                const pct = Math.min(100, Math.round((spend / total) * 100));
                return (
                  <div key={taskName} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-mono text-zinc-300">{taskName}</span>
                      <span className="font-mono text-indigo-300">
                        ${spend.toFixed(4)} ({pct}%)
                      </span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
                      <div className="h-full rounded-full bg-indigo-500" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
          <h3 className="text-sm font-semibold text-zinc-200 border-b border-zinc-800/80 pb-2">
            🤖 模型开销分布 (Model Spend Distribution)
          </h3>
          <div className="mt-3 space-y-2.5">
            {Object.keys(summary.model_spend_distribution).length === 0 ? (
              <div className="py-4 text-center text-xs text-zinc-500">暂无模型分摊记录</div>
            ) : (
              Object.entries(summary.model_spend_distribution).map(([modelName, spend]) => {
                const total = summary.total_actual_usd || summary.total_estimated_usd || 1;
                const pct = Math.min(100, Math.round((spend / total) * 100));
                return (
                  <div key={modelName} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-mono text-zinc-300">{modelName}</span>
                      <span className="font-mono text-emerald-400">
                        ${spend.toFixed(4)} ({pct}%)
                      </span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
                      <div className="h-full rounded-full bg-emerald-500" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* 复合账本明细流水穿透表 */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800/80 pb-3">
          <div className="flex items-center space-x-2">
            <h3 className="text-sm font-semibold text-zinc-200">
              📊 六维复合账本流水明细 (session_model_usage)
            </h3>
            <span className="text-xs text-zinc-500">({filteredRecords.length} 笔)</span>
          </div>

          {uniqueTasks.length > 0 && (
            <div className="flex items-center space-x-2">
              <span className="text-xs text-zinc-400">任务过滤:</span>
              <select
                value={selectedTaskFilter}
                onChange={(e) => setSelectedTaskFilter(e.target.value)}
                className="rounded-md border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-xs text-zinc-300 focus:border-indigo-500 focus:outline-none"
              >
                <option value="ALL">全部任务 (All Tasks)</option>
                {uniqueTasks.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {filteredRecords.length === 0 ? (
          <div className="py-8 text-center text-xs text-zinc-500">暂无复合账本记录</div>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-zinc-800 bg-zinc-900/60 font-medium text-zinc-400">
                <tr>
                  <th className="py-2.5 px-3">会话 ID / Task 归因</th>
                  <th className="py-2.5 px-3">模型 &amp; 提供商</th>
                  <th className="py-2.5 px-3">调用次数</th>
                  <th className="py-2.5 px-3">Token 分布 (入/出/缓)</th>
                  <th className="py-2.5 px-3">估算成本</th>
                  <th className="py-2.5 px-3">实际扣费</th>
                  <th className="py-2.5 px-3">对账状态</th>
                  {onReconcile && <th className="py-2.5 px-3">操作</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {filteredRecords.map((r) => {
                  const badge = getStatusBadge(r.cost_status, r.discrepancy_pct);
                  return (
                    <tr key={`${r.session_id}_${r.model}_${r.task}`} className="hover:bg-zinc-900/50">
                      <td className="py-2.5 px-3">
                        <div className="font-mono text-zinc-200">{r.session_id}</div>
                        <span className="inline-block mt-0.5 rounded bg-indigo-950/60 border border-indigo-800/40 px-1.5 py-0.2 text-[10px] text-indigo-300 font-mono">
                          {r.task}
                        </span>
                      </td>
                      <td className="py-2.5 px-3">
                        <div className="font-mono text-zinc-300">{r.model}</div>
                        <div className="text-[10px] text-zinc-500">{r.billing_provider}</div>
                      </td>
                      <td className="py-2.5 px-3 font-mono text-zinc-300">{r.api_call_count}</td>
                      <td className="py-2.5 px-3 font-mono text-[11px] text-zinc-400">
                        {r.input_tokens.toLocaleString()} / {r.output_tokens.toLocaleString()} / {r.cache_read_tokens.toLocaleString()}
                      </td>
                      <td className="py-2.5 px-3 font-mono text-zinc-200">
                        ${r.estimated_cost_usd.toFixed(4)}
                      </td>
                      <td className="py-2.5 px-3 font-mono text-emerald-400">
                        ${r.actual_cost_usd.toFixed(4)}
                      </td>
                      <td className="py-2.5 px-3">
                        <span className={`inline-block rounded border px-2 py-0.5 text-[10px] font-semibold ${badge.cls}`}>
                          {badge.text}
                        </span>
                      </td>
                      {onReconcile && (
                        <td className="py-2.5 px-3">
                          <button
                            type="button"
                            onClick={() => onReconcile(r, r.estimated_cost_usd)}
                            className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-[10px] text-zinc-300 hover:bg-zinc-700"
                          >
                            核销对账
                          </button>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
