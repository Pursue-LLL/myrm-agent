/**
 * ActiveTaskDrainSafetyBanner - 活动长任务防误杀与智能排空安全建议横幅
 *
 * [INPUT]
 * - safetyCheck: ActiveTaskDrainSafetyCheck 活动长任务安全排查结果
 * - onSelectStrategy?: (strategy: 'drain_first' | 'checkpoint_and_upgrade') => void
 *
 * [OUTPUT]
 * - ActiveTaskDrainSafetyBanner: React.FC
 *
 * [POS]
 * 系统一键升级前置安全防护横幅。识别活动中的 Goal/Cron 并阻断暴力重启，
 * 彻底消除升级杀掉唯一存活 Agent 导致灾难性失联的技术隐患。
 */

import React from 'react';
import {
  AlertTriangle,
  Clock,
  Save,
  ShieldCheck,
} from 'lucide-react';
import type { ActiveTaskDrainSafetyCheck } from './upgradeCockpitTypes';

export interface ActiveTaskDrainSafetyBannerProps {
  safetyCheck: ActiveTaskDrainSafetyCheck;
  onSelectStrategy?: (strategy: 'drain_first' | 'checkpoint_and_upgrade') => void;
}

export const ActiveTaskDrainSafetyBanner: React.FC<ActiveTaskDrainSafetyBannerProps> = ({
  safetyCheck,
  onSelectStrategy,
}) => {
  const isSafe = safetyCheck.recommendation === 'safe_to_reload';

  if (isSafe) {
    return (
      <div
        data-testid="task-safety-banner-safe"
        className="flex items-center gap-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-800 dark:text-emerald-300"
      >
        <ShieldCheck className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
        <div className="flex-1">
          <span className="font-semibold">运行态健康安全：</span>
          <span>{safetyCheck.recommendationRationale}</span>
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid="task-safety-banner-active-tasks"
      className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3.5 text-xs text-amber-900 dark:text-amber-200"
    >
      <div className="flex items-start gap-2.5">
        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
        <div className="flex-1 space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-amber-800 dark:text-amber-300">
              活动长任务防误杀保护（已拦截暴力重启）
            </span>
            <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-mono font-medium">
              {safetyCheck.activeTaskCount} 个任务执行中
            </span>
          </div>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            {safetyCheck.recommendationRationale}
          </p>

          {/* 活动任务列表 */}
          {safetyCheck.activeTasks.length > 0 && (
            <div className="mt-2 space-y-1.5 border-t border-amber-500/20 pt-2">
              {safetyCheck.activeTasks.map((task) => (
                <div
                  key={task.id}
                  className="flex items-center justify-between rounded bg-background/60 px-2 py-1 text-[11px] font-mono text-foreground"
                >
                  <span className="truncate max-w-[240px]">{task.title}</span>
                  <span className="text-primary font-semibold">{task.progressPercent}%</span>
                </div>
              ))}
            </div>
          )}

          {/* 决策操作栏 */}
          <div className="mt-3 flex items-center gap-2 pt-1">
            <button
              type="button"
              data-testid="drain-first-strategy-btn"
              onClick={() => {
                if (onSelectStrategy) {
                  onSelectStrategy('drain_first');
                }
              }}
              className="flex items-center gap-1 rounded bg-amber-600 px-2.5 py-1 text-[11px] font-medium text-white shadow-sm transition-colors hover:bg-amber-700"
            >
              <Clock className="h-3 w-3" />
              <span>等待当前任务完成自动重载</span>
            </button>
            <button
              type="button"
              data-testid="checkpoint-upgrade-strategy-btn"
              onClick={() => {
                if (onSelectStrategy) {
                  onSelectStrategy('checkpoint_and_upgrade');
                }
              }}
              className="flex items-center gap-1 rounded border border-amber-600/50 bg-background/80 px-2.5 py-1 text-[11px] font-medium text-foreground transition-colors hover:bg-accent/40"
            >
              <Save className="h-3 w-3 text-muted-foreground" />
              <span>保存 Checkpoint 即刻升级</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
