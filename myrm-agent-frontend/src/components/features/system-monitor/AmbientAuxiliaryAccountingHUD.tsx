/**
 * [INPUT]: AmbientAccountingReportData, AuxiliaryUsageSnapshotItem[] and action callbacks.
 * [OUTPUT]: AmbientAuxiliaryAccountingHUD React component visualizing ambient auxiliary task accounting and prompt cache purity.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/AmbientAuxiliaryAccountingHUD.tsx
 */

import React, { useState } from 'react';
import {
  AmbientAccountingReportData,
  AmbientAuxiliaryAccountingHUDProps,
  AuxiliaryUsageSnapshotItem,
  TaskCostSummaryItem,
} from './ambientAuxiliaryAccountingTypes';

export const AmbientAuxiliaryAccountingHUD: React.FC<AmbientAuxiliaryAccountingHUDProps> = ({
  report,
  snapshots = [],
  onRefresh,
  onReset,
  isRefreshing = false,
}) => {
  const [selectedTaskFilter, setSelectedTaskFilter] = useState<string>('ALL');

  const filteredSnapshots = snapshots.filter((s) => {
    if (selectedTaskFilter === 'ALL') return true;
    return s.effective_task_name === selectedTaskFilter || s.task_type === selectedTaskFilter;
  });

  const getTaskBadgeClass = (taskName: string): string => {
    if (taskName === 'main_dialogue') {
      return 'border-sky-500/40 bg-sky-500/10 text-sky-300';
    }
    if (taskName.includes('compression') || taskName.includes('compaction')) {
      return 'border-amber-500/40 bg-amber-500/10 text-amber-300';
    }
    if (taskName.includes('vision')) {
      return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300';
    }
    if (taskName.includes('eval') || taskName.includes('reflection')) {
      return 'border-purple-500/40 bg-purple-500/10 text-purple-300';
    }
    return 'border-zinc-700 bg-zinc-800 text-zinc-300';
  };

  const uniqueTaskNames = Array.from(new Set(snapshots.map((s) => s.effective_task_name)));

  return (
    <div className="flex flex-col space-y-6 rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-xl">
      {/* 头部标题与控制栏 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center space-x-3">
            <span className="text-xl font-bold tracking-tight text-white">
              环境感知式用量记账与任务归因 HUD
            </span>
            <span
              className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                report.prompt_cache_purity_preserved
                  ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400'
                  : 'border-rose-500/40 bg-rose-500/10 text-rose-400'
              }`}
            >
              {report.prompt_cache_purity_preserved ? '✓ Prompt Cache 纯度隔离已保护' : '⚠️ 缓存污染风险'}
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            区分主干会话与后台派生任务（截图处理、记忆摘要、异步评估），杜绝派生负载稀释核心对话预算与污染主干缓存
          </p>
        </div>
        <div className="flex items-center space-x-3">
          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={isRefreshing}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-200 transition hover:bg-zinc-800 disabled:opacity-50"
            >
              {isRefreshing ? '刷新中...' : '刷新大盘'}
            </button>
          )}
          {onReset && (
            <button
              onClick={() => {
                void onReset();
              }}
              className="rounded-lg border border-rose-900/60 bg-rose-950/40 px-3 py-1.5 text-xs font-medium text-rose-300 transition hover:bg-rose-900/60"
            >
              清空用量
            </button>
          )}
        </div>
      </div>

      {/* 4 大核心指标卡 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* 卡片 1: 总用量与费用 */}
        <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/50 p-4">
          <div className="text-xs font-medium text-zinc-400">调用总览 / 累计费用</div>
          <div className="mt-2 text-2xl font-bold text-white">
            ${report.total_cost_usd.toFixed(4)}
          </div>
          <div className="mt-1 text-xs text-zinc-500">
            总调用次数: <span className="font-semibold text-zinc-300">{report.total_invocations}</span> 次
          </div>
        </div>

        {/* 卡片 2: 核心主对话费用 */}
        <div className="rounded-lg border border-sky-900/40 bg-sky-950/20 p-4">
          <div className="text-xs font-medium text-sky-400">核心主对话支出 (Main Dialogue)</div>
          <div className="mt-2 text-2xl font-bold text-sky-200">
            ${report.core_dialogue_cost_usd.toFixed(4)}
          </div>
          <div className="mt-1 text-xs text-sky-400/80">
            占主干比例:{' '}
            <span className="font-semibold text-sky-200">
              {(100 - report.auxiliary_cost_share_pct).toFixed(1)}%
            </span>
          </div>
        </div>

        {/* 卡片 3: 旁路辅助任务费用 */}
        <div className="rounded-lg border border-amber-900/40 bg-amber-950/20 p-4">
          <div className="text-xs font-medium text-amber-400">旁路辅助任务支出 (Auxiliary Backstage)</div>
          <div className="mt-2 text-2xl font-bold text-amber-200">
            ${report.auxiliary_cost_usd.toFixed(4)}
          </div>
          <div className="mt-1 text-xs text-amber-400/80">
            旁路分摊占比:{' '}
            <span className="font-semibold text-amber-200">
              {report.auxiliary_cost_share_pct.toFixed(1)}%
            </span>
          </div>
        </div>

        {/* 卡片 4: 缓存隔离健康态 */}
        <div className="rounded-lg border border-emerald-900/40 bg-emerald-950/20 p-4">
          <div className="text-xs font-medium text-emerald-400">Prompt Cache 隔离保护</div>
          <div className="mt-2 text-2xl font-bold text-emerald-300">
            {report.prompt_cache_purity_preserved ? '100% 隔离' : '隔离失效'}
          </div>
          <div className="mt-1 text-xs text-emerald-400/80">
            自动环境变量上下文已生效，零历史污染
          </div>
        </div>
      </div>

      {/* 任务维度精准归因表 */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold tracking-wide text-zinc-200">
          任务维度归因与支出占比 (Task Dimension Breakdown)
        </h3>
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-left text-xs text-zinc-300">
            <thead className="border-b border-zinc-800 bg-zinc-900/80 text-zinc-400">
              <tr>
                <th className="px-4 py-2.5 font-medium">任务分类 / 维度</th>
                <th className="px-4 py-2.5 font-medium">调用次数</th>
                <th className="px-4 py-2.5 font-medium">输入 / 输出 Tokens</th>
                <th className="px-4 py-2.5 font-medium">单次均耗时</th>
                <th className="px-4 py-2.5 font-medium">费用支出 ($)</th>
                <th className="px-4 py-2.5 font-medium">支出占比</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60 bg-zinc-950/40">
              {report.task_summaries.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-zinc-500">
                    暂无任务维度调用记录
                  </td>
                </tr>
              ) : (
                report.task_summaries.map((task: TaskCostSummaryItem) => (
                  <tr key={task.task_name} className="hover:bg-zinc-900/40">
                    <td className="px-4 py-3 font-mono font-medium text-zinc-200">
                      <span className={`inline-block rounded border px-2 py-0.5 text-xs ${getTaskBadgeClass(task.task_name)}`}>
                        {task.task_name}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-zinc-300">{task.call_count}</td>
                    <td className="px-4 py-3 text-zinc-400">
                      <span className="text-zinc-200">{task.total_input_tokens.toLocaleString()}</span> /{' '}
                      <span className="text-zinc-200">{task.total_output_tokens.toLocaleString()}</span>
                    </td>
                    <td className="px-4 py-3 text-zinc-300">{task.avg_duration_ms.toFixed(1)} ms</td>
                    <td className="px-4 py-3 font-mono font-semibold text-emerald-400">
                      ${task.total_cost_usd.toFixed(5)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center space-x-2">
                        <div className="h-2 w-24 overflow-hidden rounded-full bg-zinc-800">
                          <div
                            className="h-full bg-amber-500"
                            style={{ width: `${Math.min(100, task.share_pct)}%` }}
                          />
                        </div>
                        <span className="text-xs font-medium text-zinc-400">
                          {task.share_pct.toFixed(1)}%
                        </span>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 最近调用快照事件流 */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold tracking-wide text-zinc-200">
            最近调用快照事件流 (Recent Auxiliary Snapshots)
          </h3>
          {uniqueTaskNames.length > 0 && (
            <div className="flex items-center space-x-2">
              <span className="text-xs text-zinc-400">筛选任务:</span>
              <select
                aria-label="筛选任务"
                value={selectedTaskFilter}
                onChange={(e) => setSelectedTaskFilter(e.target.value)}
                className="rounded border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-xs text-zinc-200 outline-none"
              >
                <option value="ALL">全部任务 ({snapshots.length})</option>
                {uniqueTaskNames.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-left text-xs text-zinc-300">
            <thead className="border-b border-zinc-800 bg-zinc-900/80 text-zinc-400">
              <tr>
                <th className="px-4 py-2.5 font-medium">Session ID</th>
                <th className="px-4 py-2.5 font-medium">归属任务</th>
                <th className="px-4 py-2.5 font-medium">模型</th>
                <th className="px-4 py-2.5 font-medium">Token 消耗</th>
                <th className="px-4 py-2.5 font-medium">调用耗时</th>
                <th className="px-4 py-2.5 font-medium">消耗费用 ($)</th>
                <th className="px-4 py-2.5 font-medium">时间</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60 bg-zinc-950/40">
              {filteredSnapshots.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-6 text-center text-zinc-500">
                    暂无快照数据
                  </td>
                </tr>
              ) : (
                filteredSnapshots.slice(0, 50).map((s: AuxiliaryUsageSnapshotItem, idx: number) => (
                  <tr key={`${s.session_id}-${s.timestamp_ms}-${idx}`} className="hover:bg-zinc-900/40">
                    <td className="px-4 py-2.5 font-mono text-zinc-300">{s.session_id}</td>
                    <td className="px-4 py-2.5">
                      <span className={`inline-block rounded border px-2 py-0.5 text-xs ${getTaskBadgeClass(s.effective_task_name)}`}>
                        {s.effective_task_name}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-zinc-300">{s.model}</td>
                    <td className="px-4 py-2.5 text-zinc-400">
                      {s.total_tokens.toLocaleString()} (入 {s.input_tokens} / 出 {s.output_tokens})
                    </td>
                    <td className="px-4 py-2.5 text-zinc-300">{s.duration_ms.toFixed(1)} ms</td>
                    <td className="px-4 py-2.5 font-mono font-medium text-emerald-400">
                      ${s.cost_usd.toFixed(5)}
                    </td>
                    <td className="px-4 py-2.5 text-zinc-500">
                      {new Date(s.timestamp_ms).toLocaleTimeString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
