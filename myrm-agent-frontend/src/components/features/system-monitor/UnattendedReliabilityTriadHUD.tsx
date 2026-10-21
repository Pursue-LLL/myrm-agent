/**
 * [INPUT]: UnattendedReliabilityTriadHUDProps containing triad scoreData, benchmark triggers, and refresh.
 * [OUTPUT]: UnattendedReliabilityTriadHUD React component visualizing resume, zero duplicate side-effects, and honest blocker metrics.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/UnattendedReliabilityTriadHUD.tsx
 */

import React, { useState } from 'react';
import {
  FinalReportingStatusType,
  ResumeStatusType,
  RunReliabilityRecordItem,
  SideEffectStatusType,
  UnattendedReliabilityTriadHUDProps,
} from './unattendedReliabilityTypes';

export const UnattendedReliabilityTriadHUD: React.FC<UnattendedReliabilityTriadHUDProps> = ({
  scoreData,
  onRefresh,
  onRunBenchmark,
  onReset,
  isRefreshing = false,
  isRunningBenchmark = false,
}) => {
  const [localRunningBenchmark, setLocalRunningBenchmark] = useState<boolean>(false);

  const handleRunBenchmark = async () => {
    if (!onRunBenchmark) return;
    setLocalRunningBenchmark(true);
    try {
      await onRunBenchmark();
    } finally {
      setLocalRunningBenchmark(false);
    }
  };

  const getCompositeBadge = (score: number) => {
    if (score >= 95) {
      return {
        text: '工业级无人值守 (Production-Grade)',
        cls: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
      };
    }
    if (score >= 80) {
      return {
        text: '良好可靠性 (Good Reliability)',
        cls: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
      };
    }
    return {
      text: '⚠️ 可靠性隐患 (Reliability Alert)',
      cls: 'border-rose-500/30 bg-rose-500/10 text-rose-400',
    };
  };

  const getResumeBadgeClass = (status: ResumeStatusType) => {
    switch (status) {
      case 'RESUMED_SUCCESS':
        return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400';
      case 'RESUMED_FAILED':
        return 'border-rose-500/30 bg-rose-500/10 text-rose-400';
      default:
        return 'border-zinc-700 bg-zinc-800 text-zinc-400';
    }
  };

  const getSideEffectBadgeClass = (status: SideEffectStatusType) => {
    switch (status) {
      case 'ZERO_DUPLICATE':
      case 'NO_SIDE_EFFECTS':
        return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400';
      case 'DUPLICATE_DETECTED':
        return 'border-rose-500/30 bg-rose-500/10 text-rose-400';
      default:
        return 'border-zinc-700 bg-zinc-800 text-zinc-400';
    }
  };

  const getReportingBadgeClass = (status: FinalReportingStatusType) => {
    switch (status) {
      case 'GENUINE_SUCCESS':
        return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400';
      case 'HONEST_BLOCKER':
        return 'border-sky-500/30 bg-sky-500/10 text-sky-300';
      case 'HALLUCINATED_SUCCESS':
        return 'border-rose-600 bg-rose-950/60 text-rose-300 font-bold';
      default:
        return 'border-zinc-700 bg-zinc-800 text-zinc-400';
    }
  };

  const compositeBadge = getCompositeBadge(scoreData.composite_triad_score);
  const benchmarkActive = isRunningBenchmark || localRunningBenchmark;

  return (
    <div className="flex flex-col space-y-6 rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-xl">
      {/* 头部标题与控制栏 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center space-x-3">
            <span className="text-xl font-bold tracking-tight text-white">
              无人值守可靠性三联自证 HUD (Unattended Reliability Triad)
            </span>
            <span
              className={`rounded-md border px-2.5 py-0.5 font-mono text-xs font-medium ${compositeBadge.cls}`}
            >
              {compositeBadge.text}
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            拒绝单轮虚荣刷榜 · 锚定“重启后续跑、重复执行零副作用、阻断如实上报”三大无人值守可靠性命门
          </p>
        </div>

        <div className="flex items-center space-x-3">
          {onRunBenchmark && (
            <button
              type="button"
              onClick={handleRunBenchmark}
              disabled={benchmarkActive}
              className="inline-flex items-center rounded-lg border border-emerald-600/40 bg-emerald-950/40 px-3 py-1.5 text-xs font-semibold text-emerald-300 transition-colors hover:bg-emerald-900/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            >
              {benchmarkActive ? '⚡ 正在复跑自证验收...' : '⚡ 复跑自证验收用例'}
            </button>
          )}

          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={isRefreshing}
              className="inline-flex items-center rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-200 transition-colors hover:bg-zinc-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            >
              {isRefreshing ? '刷新中...' : '刷新'}
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

      {/* 三联核心雷达卡片与综合得分 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* 综合得分 */}
        <div className="flex flex-col justify-between rounded-lg border border-zinc-800/80 bg-zinc-900/70 p-4">
          <span className="text-xs font-medium text-zinc-400">三联自证综合可靠分 (Triad Score)</span>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="font-mono text-3xl font-extrabold text-white">
              {scoreData.composite_triad_score}
            </span>
            <span className="text-xs text-zinc-500">满分 100</span>
          </div>
          <span className="mt-2 text-[11px] text-zinc-400">
            已评估任务: {scoreData.total_evaluated_runs} 次
          </span>
        </div>

        {/* 1. 重启后续跑率 */}
        <div className="flex flex-col justify-between rounded-lg border border-zinc-800/80 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-emerald-400">1. 重启后续跑率 (Resume Rate)</span>
            <span className="font-mono text-xs text-zinc-500">权重 30%</span>
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="font-mono text-2xl font-bold text-emerald-300">
              {scoreData.resume_rate_pct}%
            </span>
            <span className="text-xs text-zinc-500">失败: {scoreData.failed_resume_count}</span>
          </div>
          <p className="mt-1 text-[11px] text-zinc-500">
            沙箱/容器重启后 Durable Guardian 自动断点拉起成功率
          </p>
        </div>

        {/* 2. 重复执行零副作用率 */}
        <div className="flex flex-col justify-between rounded-lg border border-zinc-800/80 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-indigo-400">
              2. 零重复副作用率 (Zero Side-Effects)
            </span>
            <span className="font-mono text-xs text-zinc-500">权重 35%</span>
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="font-mono text-2xl font-bold text-indigo-300">
              {scoreData.zero_duplicate_side_effect_rate_pct}%
            </span>
            <span className="text-xs text-zinc-500">
              重写违规: {scoreData.duplicate_side_effect_count}
            </span>
          </div>
          <p className="mt-1 text-[11px] text-zinc-500">
            重发或重试时 ReplayAuditor 拦截外部写操作与重复扣款
          </p>
        </div>

        {/* 3. 阻塞如实上报率 */}
        <div className="flex flex-col justify-between rounded-lg border border-zinc-800/80 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-sky-400">
              3. 阻断如实上报率 (Honest Blocker)
            </span>
            <span className="font-mono text-xs text-zinc-500">权重 35%</span>
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="font-mono text-2xl font-bold text-sky-300">
              {scoreData.honest_blocker_rate_pct}%
            </span>
            <span
              className={`text-xs ${
                scoreData.hallucinated_success_count > 0
                  ? 'font-bold text-rose-400'
                  : 'text-zinc-500'
              }`}
            >
              幻觉谎报: {scoreData.hallucinated_success_count}
            </span>
          </div>
          <p className="mt-1 text-[11px] text-zinc-500">
            遇到不可逾越障碍如实阻断，绝对禁止谎称执行成功
          </p>
        </div>
      </div>

      {/* 最近无人值守自证流水审计列表 */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
        <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
          <span className="text-sm font-semibold text-white">
            无人值守运行自证审计流水 (Recent Run Evidence)
          </span>
          <span className="text-xs text-zinc-400">
            共 {scoreData.recent_records?.length || 0} 条执行事实
          </span>
        </div>

        <div className="mt-3 max-h-64 overflow-y-auto space-y-2.5">
          {!scoreData.recent_records || scoreData.recent_records.length === 0 ? (
            <div className="py-6 text-center text-xs text-zinc-500">
              暂无无人值守运行记录，点击上方「⚡ 复跑自证验收用例」立即体验自证流水
            </div>
          ) : (
            scoreData.recent_records.map((rec: RunReliabilityRecordItem) => (
              <div
                key={rec.run_id}
                className="flex flex-wrap items-center justify-between rounded-lg border border-zinc-800/80 bg-zinc-950/70 p-3 text-xs"
              >
                <div className="flex flex-col space-y-1">
                  <div className="flex items-center space-x-2">
                    <span className="font-mono font-semibold text-zinc-200">{rec.task_name}</span>
                    <span className="font-mono text-[10px] text-zinc-500">{rec.run_id}</span>
                  </div>
                  <span className="text-[11px] text-zinc-400">{rec.detail || '无附加审计说明'}</span>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-2 sm:mt-0">
                  <span
                    className={`rounded border px-2 py-0.5 font-mono text-[10px] ${getResumeBadgeClass(
                      rec.resume_status
                    )}`}
                    title="重启后续跑状态"
                  >
                    {rec.resume_status}
                  </span>

                  <span
                    className={`rounded border px-2 py-0.5 font-mono text-[10px] ${getSideEffectBadgeClass(
                      rec.side_effect_status
                    )}`}
                    title="重复副作用状态"
                  >
                    {rec.side_effect_status}
                  </span>

                  <span
                    className={`rounded border px-2 py-0.5 font-mono text-[10px] ${getReportingBadgeClass(
                      rec.reporting_status
                    )}`}
                    title="终态如实上报状态"
                  >
                    {rec.reporting_status}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
