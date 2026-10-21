/**
 * P0 Urgency Cruise Control Panel Component
 * P0 紧急高频纠偏巡航面板：5分钟看门狗倒计时、偏离拦截统计与原地 Steering 注入日志
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. a11y 无障碍标准与紧凑折叠交互。
 */

import React, { useState, useEffect } from 'react';
import {
  ShieldAlert,
  Clock,
  Compass,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  PowerOff,
  Flame,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
import { P0WatchdogLogEntry } from './templateBotTypes';
import { useTemplateBotStore } from './useTemplateBotStore';

export interface P0UrgencyCruiseControlPanelProps {
  className?: string;
  defaultTaskId?: string;
}

export const P0UrgencyCruiseControlPanel: React.FC<
  P0UrgencyCruiseControlPanelProps
> = ({ className = '', defaultTaskId = 'task-urgent-current' }) => {
  const [isLogsDrawerOpen, setIsLogsDrawerOpen] = useState<boolean>(false);

  const {
    p0CruiseState,
    activateP0UrgencyMode,
    deactivateP0UrgencyMode,
    runWatchdogInspection,
    tickCountdown,
  } = useTemplateBotStore();

  // 每秒驱动倒计时推进
  useEffect(() => {
    if (!p0CruiseState.isActive) {
      return;
    }

    const interval = setInterval(() => {
      tickCountdown();
    }, 1000);

    return () => {
      clearInterval(interval);
    };
  }, [p0CruiseState.isActive, tickCountdown]);

  if (!p0CruiseState.isActive) {
    return (
      <div
        data-testid="p0-urgency-inactive-container"
        className={`inline-flex items-center ${className}`}
      >
        <button
          type="button"
          data-testid="activate-p0-urgency-btn"
          onClick={() => {
            activateP0UrgencyMode(defaultTaskId);
          }}
          className="group flex items-center gap-1.5 rounded-full border border-neutral-800 bg-neutral-900/90 px-3 py-1 text-xs text-neutral-300 hover:border-rose-500/50 hover:bg-rose-950/20 hover:text-rose-300 transition-all shadow-sm"
          title="点击激活最高优先级 P0 紧急高频纠偏巡航模式"
        >
          <Flame className="h-3.5 w-3.5 text-neutral-400 group-hover:text-rose-400 transition-colors" />
          <span className="font-mono text-[11px] font-semibold">P0 紧急模式</span>
        </button>
      </div>
    );
  }

  const formatCountdown = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    const mm = mins < 10 ? `0${mins}` : `${mins}`;
    const ss = secs < 10 ? `0${secs}` : `${secs}`;
    return `${mm}:${ss}`;
  };

  const progressPercent = Math.min(
    100,
    Math.max(
      0,
      ((300 - p0CruiseState.nextInspectionCountdownSeconds) / 300) * 100
    )
  );

  return (
    <div
      data-testid="p0-urgency-cruise-panel"
      className={`relative flex flex-col rounded-2xl border border-rose-500/50 bg-rose-950/30 p-3.5 text-neutral-100 shadow-xl backdrop-blur-md space-y-3 ${className}`}
    >
      {/* 顶部状态与倒计时 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-rose-900/40 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-rose-500/20 text-rose-400">
            <ShieldAlert className="h-4 w-4 animate-pulse" />
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-rose-200">
                P0 紧急高频巡航模式已激活
              </span>
              <span className="rounded bg-rose-500/30 px-1.5 py-0.2 font-mono text-[10px] text-rose-300 font-bold">
                5MIN 看门狗
              </span>
            </div>
            <div className="text-[10px] text-neutral-400 font-mono truncate max-w-sm">
              任务：{p0CruiseState.taskTitle}
            </div>
          </div>
        </div>

        {/* 倒计时与控制按钮 */}
        <div className="flex items-center gap-2 self-end sm:self-auto shrink-0">
          <div className="flex items-center gap-1 font-mono text-xs text-rose-300 bg-rose-950/60 border border-rose-800/60 px-2 py-0.5 rounded-lg">
            <Clock className="h-3 w-3" />
            <span data-testid="watchdog-countdown-text">
              {formatCountdown(p0CruiseState.nextInspectionCountdownSeconds)}
            </span>
          </div>

          <button
            type="button"
            data-testid="trigger-manual-inspection-btn"
            onClick={() => {
              runWatchdogInspection();
            }}
            className="flex items-center gap-1 rounded-lg border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs text-neutral-300 hover:bg-neutral-800 hover:text-white transition-colors"
            title="立即执行一次看门狗轨迹审查"
          >
            <RefreshCw className="h-3 w-3" />
            <span className="text-[11px] hidden sm:inline">立即巡检</span>
          </button>

          <button
            type="button"
            data-testid="deactivate-p0-btn"
            onClick={deactivateP0UrgencyMode}
            className="flex items-center gap-1 rounded-lg bg-neutral-800 px-2 py-1 text-xs text-rose-400 hover:bg-rose-950/60 hover:text-rose-300 transition-colors"
            title="关闭 P0 紧急模式"
          >
            <PowerOff className="h-3 w-3" />
            <span className="text-[11px] hidden sm:inline">退出</span>
          </button>
        </div>
      </div>

      {/* 5分钟巡检进度条 */}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-neutral-900 border border-neutral-800">
        <div
          data-testid="p0-countdown-progress"
          className="h-full rounded-full bg-gradient-to-r from-rose-500 to-amber-400 transition-all duration-300"
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      {/* 指标卡片：纠偏统计与日志折叠开关 */}
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-3 font-mono text-[11px]">
          <span className="flex items-center gap-1 text-neutral-300">
            <Compass className="h-3.5 w-3.5 text-cyan-400" />
            <span>
              已拦截偏离：
              <b
                data-testid="deviation-count-badge"
                className="text-amber-400 font-bold"
              >
                {p0CruiseState.deviationInterceptCount}
              </b>
            </span>
          </span>

          <span className="text-neutral-600">|</span>

          <span className="text-neutral-300">
            原地 Steering 注入：
            <b
              data-testid="steering-count-badge"
              className="text-rose-400 font-bold"
            >
              {p0CruiseState.steeringInjectedCount}
            </b>
          </span>
        </div>

        <button
          type="button"
          data-testid="toggle-watchdog-logs-btn"
          onClick={() => {
            setIsLogsDrawerOpen(!isLogsDrawerOpen);
          }}
          className="flex items-center gap-1 text-[11px] text-neutral-400 hover:text-white transition-colors"
        >
          <span>巡检日志 ({p0CruiseState.watchdogLogs.length})</span>
          {isLogsDrawerOpen ? (
            <ChevronUp className="h-3 w-3" />
          ) : (
            <ChevronDown className="h-3 w-3" />
          )}
        </button>
      </div>

      {/* 巡检日志展开抽屉 */}
      {isLogsDrawerOpen && (
        <div
          data-testid="watchdog-logs-drawer"
          className="max-h-40 overflow-y-auto rounded-xl border border-rose-900/40 bg-neutral-950/80 p-2.5 space-y-2 text-xs"
        >
          {p0CruiseState.watchdogLogs.length === 0 ? (
            <div className="text-center py-2 text-[11px] text-neutral-500 font-mono">
              看门狗尚未生成巡检记录，将在下一次周期触发。
            </div>
          ) : (
            p0CruiseState.watchdogLogs.map((entry: P0WatchdogLogEntry) => (
              <div
                key={entry.id}
                data-testid={`watchdog-log-item-${entry.id}`}
                className="rounded-lg bg-neutral-900/90 border border-neutral-800 p-2 space-y-1"
              >
                <div className="flex items-center justify-between font-mono text-[10px]">
                  <span className="font-semibold text-neutral-300">
                    第 {entry.inspectionRound} 轮看门狗巡检
                  </span>
                  <span
                    className={`flex items-center gap-1 ${
                      entry.status === 'steered'
                        ? 'text-rose-400 font-bold'
                        : entry.status === 'warning'
                        ? 'text-amber-400'
                        : 'text-emerald-400'
                    }`}
                  >
                    {entry.status === 'steered' ? (
                      <AlertTriangle className="h-3 w-3" />
                    ) : (
                      <CheckCircle2 className="h-3 w-3" />
                    )}
                    <span className="uppercase">{entry.status}</span>
                  </span>
                </div>

                {entry.detectedIssue && (
                  <p className="text-[11px] text-amber-300">
                    {entry.detectedIssue}
                  </p>
                )}

                {entry.injectedSteeringPrompt && (
                  <div className="rounded bg-rose-950/50 border border-rose-800/40 p-1.5 text-[10px] text-rose-200 font-mono">
                    {entry.injectedSteeringPrompt}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
