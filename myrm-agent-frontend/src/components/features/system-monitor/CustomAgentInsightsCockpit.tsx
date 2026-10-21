/**
 * [INPUT]: CustomAgentInsightsCockpitProps containing operational telemetry snapshot and control triggers.
 * [OUTPUT]: CustomAgentInsightsCockpit React component visualizing intent clusters, skill funnel, and HITL friction ROI.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/CustomAgentInsightsCockpit.tsx
 */

import React, { useState } from 'react';
import {
  AgentHitlBottleneckMetricData,
  AgentIntentClusterItem,
  AgentSkillHealthMetricItem,
  CustomAgentInsightsCockpitProps,
} from './customAgentInsightsTypes';

export const CustomAgentInsightsCockpit: React.FC<CustomAgentInsightsCockpitProps> = ({
  data,
  onRefresh,
  onReset,
  onSelectAgent,
  isRefreshing = false,
}) => {
  const [isResetting, setIsResetting] = useState<boolean>(false);

  const handleReset = async () => {
    if (!onReset) return;
    setIsResetting(true);
    try {
      await onReset();
    } finally {
      setIsResetting(false);
    }
  };

  const getSuccessRateBadge = (rate: number) => {
    if (rate >= 95) {
      return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400';
    }
    if (rate >= 80) {
      return 'border-amber-500/30 bg-amber-500/10 text-amber-300';
    }
    return 'border-rose-500/30 bg-rose-500/10 text-rose-400';
  };

  const getHitlStatusBadge = (hitlRate: number) => {
    if (hitlRate <= 10) {
      return {
        text: '高度自主 (High Autonomy)',
        cls: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
      };
    }
    if (hitlRate <= 30) {
      return {
        text: '协同协作 (Collaborative)',
        cls: 'border-sky-500/30 bg-sky-500/10 text-sky-300',
      };
    }
    return {
      text: '重度依赖人工 (High Friction)',
      cls: 'border-amber-500/30 bg-amber-500/10 text-amber-400',
    };
  };

  const hitlBadge = getHitlStatusBadge(data.hitl_metrics.hitl_interception_rate_pct);

  return (
    <div className="flex flex-col space-y-6 rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-xl">
      {/* 头部标题与控制栏 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center space-x-3">
            <span className="text-xl font-bold tracking-tight text-white">
              自定义智能体运营洞察驾驶舱
            </span>
            <span className="rounded-md border border-indigo-500/30 bg-indigo-500/10 px-2.5 py-0.5 text-xs font-semibold text-indigo-300">
              Agent ID: {data.agent_id || 'Global'}
            </span>
            <span className="rounded-md border border-zinc-700 bg-zinc-800/80 px-2 py-0.5 text-xs text-zinc-400">
              近 {data.time_window_days} 天统计
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            按智能体维度聚类用户真实业务意图、追踪挂载技能漏斗健康度、度量人机卡点率与 Token 产出 ROI
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
              {isRefreshing ? '刷新中...' : '刷新洞察'}
            </button>
          )}

          {onReset && (
            <button
              type="button"
              onClick={handleReset}
              disabled={isResetting}
              className="inline-flex items-center rounded-lg border border-rose-900/50 bg-rose-950/40 px-3 py-1.5 text-xs font-medium text-rose-300 transition-colors hover:bg-rose-900/60 disabled:opacity-50"
            >
              {isResetting ? '重置中...' : '清空遥测'}
            </button>
          )}
        </div>
      </div>

      {/* 核心指标概览 4 大 KPI */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="text-xs font-medium text-zinc-400">总交互请求数</div>
          <div className="mt-2 text-2xl font-bold text-white tracking-tight">
            {data.total_interactions.toLocaleString()}
          </div>
          <div className="mt-1 text-[11px] text-zinc-500">用户发起的 Prompt 轮次</div>
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="text-xs font-medium text-zinc-400">累计 Token 消耗</div>
          <div className="mt-2 text-2xl font-bold text-indigo-300 tracking-tight">
            {data.total_tokens_consumed.toLocaleString()}
          </div>
          <div className="mt-1 text-[11px] text-zinc-500">输入与输出 Token 合计</div>
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-zinc-400">HITL 人工卡点率</span>
            <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${hitlBadge.cls}`}>
              {hitlBadge.text}
            </span>
          </div>
          <div className="mt-2 text-2xl font-bold text-amber-300 tracking-tight">
            {data.hitl_metrics.hitl_interception_rate_pct.toFixed(1)}%
          </div>
          <div className="mt-1 text-[11px] text-zinc-500">
            {data.hitl_metrics.hitl_intercepted_tasks} / {data.hitl_metrics.total_tasks} 任务触发干预
          </div>
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="text-xs font-medium text-zinc-400">工件产出 Token ROI</div>
          <div className="mt-2 text-2xl font-bold text-emerald-400 tracking-tight">
            {data.hitl_metrics.token_roi_ratio.toFixed(2)}
          </div>
          <div className="mt-1 text-[11px] text-zinc-500">每万 Token 生成可交付工件数</div>
        </div>
      </div>

      {/* 视角 1: 意图聚类分布 (Intent Clusters) */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
        <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3">
          <h3 className="text-sm font-semibold text-zinc-200">
            📊 用户真实业务意图聚类 (Top 5 场景分布)
          </h3>
          <span className="text-xs text-zinc-500">
            发现高频场景并定位智能体优化方向
          </span>
        </div>

        {data.intent_clusters.length === 0 ? (
          <div className="py-8 text-center text-xs text-zinc-500">暂无意图聚类记录</div>
        ) : (
          <div className="mt-3 space-y-3">
            {data.intent_clusters.map((cluster) => (
              <div
                key={cluster.intent_category}
                className="rounded-md border border-zinc-800/70 bg-zinc-900/80 p-3"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <span className="font-mono text-xs font-bold text-zinc-100">
                      {cluster.intent_category}
                    </span>
                    <span className="text-xs text-zinc-400">
                      ({cluster.request_count} 次)
                    </span>
                  </div>
                  <span className="text-xs font-semibold text-indigo-400">
                    {cluster.share_pct.toFixed(1)}%
                  </span>
                </div>

                {/* 分布百分比进度条 */}
                <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
                  <div
                    className="h-full rounded-full bg-indigo-500"
                    style={{ width: `${Math.min(100, cluster.share_pct)}%` }}
                  />
                </div>

                <div className="mt-2 text-[11px] text-zinc-400 truncate">
                  <span className="text-zinc-500">代表性样本：</span>
                  {cluster.sample_utterance}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 视角 2: 技能健康漏斗 (Skill Health Funnel) */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
        <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3">
          <h3 className="text-sm font-semibold text-zinc-200">
            🛠️ 挂载技能漏斗健康度 (Skill Funnel & Latency)
          </h3>
          <span className="text-xs text-zinc-500">
            监控调用成功率、P95 延迟与故障根因
          </span>
        </div>

        {data.skill_funnel.length === 0 ? (
          <div className="py-8 text-center text-xs text-zinc-500">暂无技能执行记录</div>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-zinc-800 bg-zinc-900/60 text-zinc-400 font-medium">
                <tr>
                  <th className="py-2.5 px-3">技能 / 工具名称</th>
                  <th className="py-2.5 px-3">调用次数</th>
                  <th className="py-2.5 px-3">成功率</th>
                  <th className="py-2.5 px-3">平均延迟</th>
                  <th className="py-2.5 px-3">P95 延迟</th>
                  <th className="py-2.5 px-3">Top 3 故障根因</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {data.skill_funnel.map((skill) => (
                  <tr key={skill.skill_name} className="hover:bg-zinc-900/50">
                    <td className="py-2.5 px-3 font-mono font-medium text-zinc-200">
                      {skill.skill_name}
                    </td>
                    <td className="py-2.5 px-3 text-zinc-300">
                      {skill.total_calls.toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3">
                      <span
                        className={`inline-block rounded border px-2 py-0.5 text-[11px] font-semibold ${getSuccessRateBadge(
                          skill.success_rate_pct
                        )}`}
                      >
                        {skill.success_rate_pct.toFixed(1)}%
                      </span>
                    </td>
                    <td className="py-2.5 px-3 font-mono text-zinc-400">
                      {skill.avg_latency_ms.toFixed(1)} ms
                    </td>
                    <td className="py-2.5 px-3 font-mono text-zinc-400">
                      {skill.p95_latency_ms.toFixed(1)} ms
                    </td>
                    <td className="py-2.5 px-3">
                      {skill.top_error_reasons.length === 0 ? (
                        <span className="text-zinc-600">无故障</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {skill.top_error_reasons.map((err, idx) => (
                            <span
                              key={idx}
                              className="rounded bg-rose-950/60 border border-rose-800/40 px-1.5 py-0.5 text-[10px] text-rose-300 font-mono"
                            >
                              {err}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 视角 3: 人机协同卡点阻碍度量 */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
        <h3 className="text-sm font-semibold text-zinc-200 border-b border-zinc-800/80 pb-3">
          🤝 人机协同阻碍与等待耗时 (HITL Friction Metrics)
        </h3>
        <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded-md border border-zinc-800/80 bg-zinc-900/60 p-3">
            <span className="text-[11px] text-zinc-400">拦截任务总数</span>
            <div className="mt-1 text-lg font-bold text-zinc-200">
              {data.hitl_metrics.hitl_intercepted_tasks} / {data.hitl_metrics.total_tasks}
            </div>
            <div className="text-[10px] text-zinc-500">因权限、风险门禁需确认的任务</div>
          </div>

          <div className="rounded-md border border-zinc-800/80 bg-zinc-900/60 p-3">
            <span className="text-[11px] text-zinc-400">平均人工确认等待</span>
            <div className="mt-1 text-lg font-bold text-amber-300 font-mono">
              {data.hitl_metrics.avg_approval_wait_seconds.toFixed(1)} 秒
            </div>
            <div className="text-[10px] text-zinc-500">人类操作者在审批弹窗前的停留时长</div>
          </div>

          <div className="rounded-md border border-zinc-800/80 bg-zinc-900/60 p-3">
            <span className="text-[11px] text-zinc-400">Token 生产力倍率</span>
            <div className="mt-1 text-lg font-bold text-emerald-400 font-mono">
              {data.hitl_metrics.token_roi_ratio.toFixed(2)} 份/万Token
            </div>
            <div className="text-[10px] text-zinc-500">高质工件生产转化率</div>
          </div>
        </div>
      </div>
    </div>
  );
};
