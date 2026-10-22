/**
 * [INPUT]: DeploymentFunnelDashboardProps with snapshot, refresh, and dispatch callbacks.
 * [OUTPUT]: DeploymentFunnelDashboard React component visualizing multi-stage conversion, dropoff hotspots, sentiment analysis, and autonomous goal nudges.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/DeploymentFunnelDashboard.tsx
 */

import React, { useState } from 'react';
import {
  DeploymentFunnelDashboardProps,
  FunnelStage,
  StageDropoffMetric,
} from './deploymentFunnelTypes';

const STAGE_LABELS: Record<FunnelStage, { title: string; desc: string }> = {
  STAGE_1_VIEW: { title: '1. 曝光浏览', desc: '用户进入部署主页或查看界面' },
  STAGE_2_ENGAGE: { title: '2. 深度交互', desc: '用户点击试用、配置参数或浏览详情' },
  STAGE_3_ACTION: { title: '3. 核心操作', desc: '用户执行部署物核心任务或发起调用' },
  STAGE_4_COMPLETE: { title: '4. 达成留存', desc: '用户成功完成全流程并获得最终价值' },
};

export const DeploymentFunnelDashboard: React.FC<DeploymentFunnelDashboardProps> = ({
  snapshot,
  onRefresh,
  onDispatchAutonomousGoal,
  isDispatching = false,
}) => {
  const [dispatchSuccess, setDispatchSuccess] = useState<boolean>(false);

  const handleDispatch = async () => {
    if (!snapshot.autonomous_goal_recommendation || !onDispatchAutonomousGoal) return;
    try {
      await onDispatchAutonomousGoal(snapshot.autonomous_goal_recommendation);
      setDispatchSuccess(true);
      setTimeout(() => setDispatchSuccess(false), 4000);
    } catch {
      setDispatchSuccess(false);
    }
  };

  const totalFeedback =
    snapshot.feedback_counts.POSITIVE +
    snapshot.feedback_counts.NEUTRAL +
    snapshot.feedback_counts.NEGATIVE;

  return (
    <div className="flex flex-col space-y-6 rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-xl">
      {/* 头部摘要 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center space-x-3">
            <span className="text-xl font-bold tracking-tight text-white">
              交付部署漏斗监测与反馈闭环
            </span>
            <span className="rounded-md border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-0.5 font-mono text-xs text-cyan-400">
              {snapshot.deployment_id}
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            总独立访客: <span className="font-semibold text-zinc-200">{snapshot.total_visitors}</span> 人 |
            求值时间: {new Date(snapshot.evaluated_at).toLocaleString()}
          </p>
        </div>

        <div className="flex items-center space-x-3">
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:border-zinc-500 hover:bg-zinc-800 transition"
            >
              刷新数据
            </button>
          )}
        </div>
      </div>

      {/* 漏斗 4 阶梯转化卡片网格 */}
      <div>
        <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-400">
          全链路 4 阶梯转化漏斗
        </h4>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          {snapshot.stages.map((stageItem: StageDropoffMetric, idx: number) => {
            const isHotspot = snapshot.dropoff_hotspot_stage === stageItem.stage;
            const meta = STAGE_LABELS[stageItem.stage];

            return (
              <div
                key={stageItem.stage}
                className={`relative flex flex-col justify-between rounded-lg border p-4 transition ${
                  isHotspot
                    ? 'border-rose-500/60 bg-rose-950/20 shadow-md shadow-rose-950/40'
                    : 'border-zinc-800 bg-zinc-900/60'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-zinc-200">
                      {meta?.title ?? stageItem.stage}
                    </span>
                    {isHotspot && (
                      <span className="rounded bg-rose-500/20 px-1.5 py-0.5 text-[10px] font-bold text-rose-400 border border-rose-500/30">
                        流失热点
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-[11px] text-zinc-400">{meta?.desc}</p>

                  {/* 用户数 */}
                  <div className="mt-4 flex items-baseline space-x-2">
                    <span className="text-2xl font-bold tracking-tight text-white">
                      {stageItem.user_count}
                    </span>
                    <span className="text-xs text-zinc-400">人到访</span>
                  </div>
                </div>

                {/* 转化率 & 流失率进度条 */}
                <div className="mt-4 space-y-1.5 border-t border-zinc-800/80 pt-3">
                  <div className="flex justify-between text-xs">
                    <span className="text-zinc-400">留存转化率</span>
                    <span className="font-mono font-medium text-emerald-400">
                      {stageItem.conversion_rate_pct.toFixed(1)}%
                    </span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-800">
                    <div
                      className="h-full rounded-full bg-emerald-500 transition-all duration-300"
                      style={{ width: `${Math.min(stageItem.conversion_rate_pct, 100)}%` }}
                    />
                  </div>

                  {idx > 0 && (
                    <div className="flex justify-between text-[11px] text-zinc-400">
                      <span>前序流失率</span>
                      <span
                        className={`font-mono ${
                          stageItem.dropoff_rate_pct >= 40
                            ? 'font-bold text-rose-400'
                            : 'text-zinc-400'
                        }`}
                      >
                        {stageItem.dropoff_rate_pct.toFixed(1)}%
                      </span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 用户反馈情绪统计与主动推动横幅 */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* 反馈情绪分布 */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
            用户反馈情感分布
          </h4>
          <div className="mt-3 flex items-center justify-between text-sm">
            <span className="text-zinc-400">累计反馈总数:</span>
            <span className="font-semibold text-white">{totalFeedback} 条</span>
          </div>

          <div className="mt-4 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="flex items-center space-x-1.5 text-emerald-400">
                <span className="h-2 w-2 rounded-full bg-emerald-400" />
                <span>正面满意 (Positive)</span>
              </span>
              <span className="font-mono text-zinc-200">
                {snapshot.feedback_counts.POSITIVE} 条
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="flex items-center space-x-1.5 text-zinc-300">
                <span className="h-2 w-2 rounded-full bg-zinc-400" />
                <span>中性客观 (Neutral)</span>
              </span>
              <span className="font-mono text-zinc-200">
                {snapshot.feedback_counts.NEUTRAL} 条
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="flex items-center space-x-1.5 text-rose-400">
                <span className="h-2 w-2 rounded-full bg-rose-400" />
                <span>负面吐槽 (Negative)</span>
              </span>
              <span className="font-mono font-bold text-rose-400">
                {snapshot.feedback_counts.NEGATIVE} 条
              </span>
            </div>
          </div>
        </div>

        {/* 主动 Nudge 推动与自愈闭环面板 */}
        <div
          className={`flex flex-col justify-between rounded-lg border p-4 lg:col-span-2 ${
            snapshot.nudge_required
              ? 'border-amber-500/50 bg-amber-950/15'
              : 'border-zinc-800 bg-zinc-900/40'
          }`}
        >
          <div>
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <span
                  className={`inline-block h-2.5 w-2.5 rounded-full ${
                    snapshot.nudge_required ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400'
                  }`}
                />
                <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-200">
                  {snapshot.nudge_required ? '自主 Nudge 推动警报' : '漏斗运行健康，无需推动'}
                </h4>
              </div>
              {snapshot.nudge_required && (
                <span className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-300">
                  需要介入优化
                </span>
              )}
            </div>

            {snapshot.nudge_reason && (
              <p className="mt-2 text-xs text-amber-200/90 leading-relaxed">
                <span className="font-semibold">告警原因:</span> {snapshot.nudge_reason}
              </p>
            )}

            {snapshot.autonomous_goal_recommendation && (
              <div className="mt-3 rounded border border-zinc-800 bg-zinc-900/80 p-3">
                <span className="text-[11px] font-medium text-zinc-400">
                  推荐高阶自愈目标 (Autonomous Goal Recommendation):
                </span>
                <p className="mt-1 text-xs text-cyan-300 font-mono leading-relaxed">
                  {snapshot.autonomous_goal_recommendation}
                </p>
              </div>
            )}
          </div>

          {/* 目标派发动作区 */}
          {snapshot.nudge_required && snapshot.autonomous_goal_recommendation && (
            <div className="mt-4 flex items-center justify-between border-t border-zinc-800/80 pt-3">
              <div className="text-[11px] text-zinc-400">
                {dispatchSuccess ? (
                  <span className="font-semibold text-emerald-400">
                    ✓ 高阶自愈目标已成功派发至自治 Agent 任务队列！
                  </span>
                ) : (
                  '一键将该目标派发至 Agent，由其自主阅读日志与断点代码并修复。'
                )}
              </div>
              <button
                onClick={handleDispatch}
                disabled={isDispatching || !onDispatchAutonomousGoal}
                className="rounded-lg bg-cyan-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow hover:bg-cyan-500 disabled:opacity-50 transition"
              >
                {isDispatching ? '正在派发...' : '一键派发优化目标'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
