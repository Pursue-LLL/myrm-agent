/**
 * [INPUT]: StreamMetricsCockpitProps with aggregate metrics, recent call sessions, and refresh callbacks.
 * [OUTPUT]: StreamMetricsCockpit React component visualizing clean final-outcome metrics and anti-pollution guarantees.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/StreamMetricsCockpit.tsx
 */

import React from 'react';
import {
  StreamCallOutcome,
  StreamCallSession,
  StreamMetricsCockpitProps,
} from './streamMetricsTypes';

const OUTCOME_CONFIG: Record<
  StreamCallOutcome,
  { label: string; bg: string; text: string; border: string }
> = {
  SUCCESS: {
    label: '成功完成',
    bg: 'bg-emerald-500/10',
    text: 'text-emerald-400',
    border: 'border-emerald-500/30',
  },
  ERROR: {
    label: '异常失败',
    bg: 'bg-rose-500/10',
    text: 'text-rose-400',
    border: 'border-rose-500/30',
  },
  CANCELLED: {
    label: '主动取消',
    bg: 'bg-amber-500/10',
    text: 'text-amber-400',
    border: 'border-amber-500/30',
  },
  TIMEOUT: {
    label: '超时中断',
    bg: 'bg-purple-500/10',
    text: 'text-purple-400',
    border: 'border-purple-500/30',
  },
};

export const StreamMetricsCockpit: React.FC<StreamMetricsCockpitProps> = ({
  aggregate,
  recentSessions = [],
  onRefresh,
  selectedModel,
  onSelectModel,
}) => {
  return (
    <div className="flex flex-col space-y-6 rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-xl">
      {/* 头部摘要 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center space-x-3">
            <span className="text-xl font-bold tracking-tight text-white">
              流式调用按最终结果计量驾驶舱
            </span>
            <span className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 font-mono text-xs text-emerald-400">
              防中间 Chunk 污染已生效
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            仅在流式会话终态产生唯一调用结果归因（SUCCESS / ERROR / CANCELLED / TIMEOUT），杜绝指标虚高
          </p>
        </div>

        <div className="flex items-center space-x-3">
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:border-zinc-500 hover:bg-zinc-800 transition"
            >
              刷新指标
            </button>
          )}
        </div>
      </div>

      {/* 四大核心指标卡片 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* 真实调用数 */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="flex items-center justify-between text-xs text-zinc-400">
            <span>真实结算调用数</span>
            <span className="text-[10px] text-emerald-400">1 调用 = 1 次</span>
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-3xl font-bold tracking-tight text-white">
              {aggregate.total_calls}
            </span>
            <span className="text-xs text-zinc-400">次调用</span>
          </div>
          <p className="mt-2 text-[11px] text-zinc-400">
            实际吞吐 Chunk: {aggregate.total_chunks.toLocaleString()} 个
          </p>
        </div>

        {/* 最终成功率 */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="text-xs text-zinc-400">终态成功率 (SLA)</div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-3xl font-bold tracking-tight text-emerald-400">
              {aggregate.success_rate_pct.toFixed(1)}%
            </span>
          </div>
          <div className="mt-2 flex items-center space-x-2 text-[11px] text-zinc-400">
            <span>成功: {aggregate.success_calls}</span>
            <span>·</span>
            <span>失败: {aggregate.error_calls}</span>
          </div>
        </div>

        {/* 防虚高倍数 */}
        <div className="rounded-lg border border-cyan-500/20 bg-cyan-950/10 p-4">
          <div className="flex items-center justify-between text-xs text-cyan-400">
            <span>防指标虚高倍数</span>
            <span className="rounded bg-cyan-500/20 px-1.5 py-0.2 text-[10px] font-mono">
              ANTI-POLLUTION
            </span>
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-3xl font-bold tracking-tight text-cyan-300 font-mono">
              {aggregate.chunk_inflation_ratio.toFixed(1)}×
            </span>
          </div>
          <p className="mt-2 text-[11px] text-cyan-200/80">
            已阻断 {Math.max(0, aggregate.total_chunks - aggregate.total_calls).toLocaleString()} 次中间事件干扰
          </p>
        </div>

        {/* 时延与持续时间 */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="text-xs text-zinc-400">首字时延 (TTFT) / 耗时</div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-2xl font-bold tracking-tight text-white font-mono">
              {aggregate.avg_ttft_ms.toFixed(0)} ms
            </span>
            <span className="text-xs text-zinc-400">首字</span>
          </div>
          <p className="mt-2 text-[11px] text-zinc-400 font-mono">
            平均整流: {aggregate.avg_duration_ms.toFixed(0)} ms
          </p>
        </div>
      </div>

      {/* 终态分布柱状条 */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
        <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-400">
          流式会话终态结果分布 (Final Outcomes Breakdown)
        </h4>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded border border-emerald-500/20 bg-emerald-500/5 p-3">
            <div className="text-xs text-emerald-400">成功完成 (SUCCESS)</div>
            <div className="mt-1 text-xl font-bold text-white font-mono">
              {aggregate.success_calls}
            </div>
          </div>
          <div className="rounded border border-rose-500/20 bg-rose-500/5 p-3">
            <div className="text-xs text-rose-400">异常失败 (ERROR)</div>
            <div className="mt-1 text-xl font-bold text-white font-mono">
              {aggregate.error_calls}
            </div>
          </div>
          <div className="rounded border border-amber-500/20 bg-amber-500/5 p-3">
            <div className="text-xs text-amber-400">用户取消 (CANCELLED)</div>
            <div className="mt-1 text-xl font-bold text-white font-mono">
              {aggregate.cancelled_calls}
            </div>
          </div>
          <div className="rounded border border-purple-500/20 bg-purple-500/5 p-3">
            <div className="text-xs text-purple-400">超时中断 (TIMEOUT)</div>
            <div className="mt-1 text-xl font-bold text-white font-mono">
              {aggregate.timeout_calls}
            </div>
          </div>
        </div>
      </div>

      {/* 防污染数据地基隔离说明看板 */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
        <div className="flex items-start space-x-3">
          <div className="mt-0.5 rounded-full bg-cyan-500/20 p-1 text-cyan-400">
            <svg
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <div>
            <h5 className="text-xs font-semibold text-zinc-200">
              可观测性数据地基真实性保证 (Data Integrity Guarantee)
            </h5>
            <p className="mt-1 text-xs text-zinc-400 leading-relaxed">
              在传统流式监控中，若将每个增量 chunk 事件误作为独立调用计数，系统调用量将被虚高放大至{' '}
              <span className="font-mono text-zinc-200">{aggregate.total_chunks}</span> 次；
              Myrm 严格按流的最终收敛状态（成功/失败/取消）统一归因，只记录{' '}
              <span className="font-mono font-semibold text-emerald-400">
                {aggregate.total_calls}
              </span>{' '}
              次真实调用，杜绝中间事件污染，保证模型 SLA、调用成本与成功率基线 100% 诚实。
            </p>
          </div>
        </div>
      </div>

      {/* 近期流式调用样本流水 */}
      {recentSessions.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-zinc-800">
          <div className="bg-zinc-900 px-4 py-3 border-b border-zinc-800">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-300">
              近期流式调用归因流水 (Recent Streamed Calls)
            </h4>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-zinc-300">
              <thead className="bg-zinc-950/80 text-[11px] uppercase tracking-wider text-zinc-400 border-b border-zinc-800">
                <tr>
                  <th className="px-4 py-2.5">调用 ID</th>
                  <th className="px-4 py-2.5">模型</th>
                  <th className="px-4 py-2.5">首字时延 (TTFT)</th>
                  <th className="px-4 py-2.5">总耗时</th>
                  <th className="px-4 py-2.5">Chunk 数量</th>
                  <th className="px-4 py-2.5">最终结果 (Outcome)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60 bg-zinc-900/30 font-mono text-[11px]">
                {recentSessions.map((s: StreamCallSession) => {
                  const outcomeMeta = s.outcome
                    ? OUTCOME_CONFIG[s.outcome]
                    : {
                        label: '执行中',
                        bg: 'bg-zinc-500/10',
                        text: 'text-zinc-400',
                        border: 'border-zinc-500/30',
                      };

                  return (
                    <tr key={s.call_id} className="hover:bg-zinc-800/40 transition">
                      <td className="px-4 py-2.5 text-zinc-200 font-semibold">{s.call_id}</td>
                      <td className="px-4 py-2.5 text-zinc-400">{s.model_name}</td>
                      <td className="px-4 py-2.5 text-cyan-400">
                        {s.ttft_ms !== null ? `${s.ttft_ms.toFixed(0)} ms` : '-'}
                      </td>
                      <td className="px-4 py-2.5 text-zinc-300">
                        {s.total_duration_ms !== null
                          ? `${s.total_duration_ms.toFixed(0)} ms`
                          : '-'}
                      </td>
                      <td className="px-4 py-2.5 text-zinc-400">{s.chunk_count} 个</td>
                      <td className="px-4 py-2.5">
                        <span
                          className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-sans font-medium border ${outcomeMeta.bg} ${outcomeMeta.text} ${outcomeMeta.border}`}
                        >
                          {outcomeMeta.label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
