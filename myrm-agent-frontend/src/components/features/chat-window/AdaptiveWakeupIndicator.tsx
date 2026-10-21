'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Play, Pause, AlertTriangle, CheckCircle2, RotateCcw, ShieldAlert, Cpu } from 'lucide-react';

export type WakeupChannel = 'inject' | 'followup' | 'suppress' | 'degrade';
export type HostActivityState = 'idle' | 'busy' | 'stopped';
export type WakeupSourceType = 'subagent' | 'background_job';

export interface WakeupBudgetStatus {
  session_id: string;
  consecutive_wakes: number;
  max_consecutive_wakes: number;
  budget_remaining: number;
  is_exhausted: boolean;
  is_user_stopped: boolean;
  host_activity: HostActivityState;
  last_wake_time?: string | null;
  last_human_reset_time?: string | null;
}

export interface AdaptiveWakeupIndicatorProps {
  sessionId: string;
  initialStatus?: WakeupBudgetStatus;
  activeChannel?: WakeupChannel;
  sourceSummary?: string;
  sourceType?: WakeupSourceType;
  onResetBudget?: (sessionId: string) => void;
  onStopWakeup?: (sessionId: string) => void;
  onDismiss?: () => void;
}

export const AdaptiveWakeupIndicator: React.FC<AdaptiveWakeupIndicatorProps> = ({
  sessionId,
  initialStatus,
  activeChannel = 'followup',
  sourceSummary,
  sourceType = 'background_job',
  onResetBudget,
  onStopWakeup,
  onDismiss,
}) => {
  const [status, setStatus] = useState<WakeupBudgetStatus>(
    initialStatus ?? {
      session_id: sessionId,
      consecutive_wakes: 1,
      max_consecutive_wakes: 3,
      budget_remaining: 2,
      is_exhausted: false,
      is_user_stopped: false,
      host_activity: 'idle',
    },
  );
  const [loading, setLoading] = useState(false);

  const fetchBudgetStatus = useCallback(async () => {
    try {
      const res = await fetch(`/api/agents/adaptive-wakeup/sessions/${encodeURIComponent(sessionId)}/budget`);
      if (res.ok) {
        const data: WakeupBudgetStatus = await res.json();
        setStatus(data);
      }
    } catch {
      // Offline or mocked in tests
    }
  }, [sessionId]);

  useEffect(() => {
    if (!initialStatus) {
      void fetchBudgetStatus();
    }
  }, [fetchBudgetStatus, initialStatus]);

  const handleReset = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/agents/adaptive-wakeup/sessions/${encodeURIComponent(sessionId)}/human-turn`, {
        method: 'POST',
      });
      if (res.ok) {
        const data: WakeupBudgetStatus = await res.json();
        setStatus(data);
      }
      onResetBudget?.(sessionId);
    } catch {
      setStatus((prev) => ({
        ...prev,
        consecutive_wakes: 0,
        budget_remaining: prev.max_consecutive_wakes,
        is_exhausted: false,
        is_user_stopped: false,
      }));
      onResetBudget?.(sessionId);
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/agents/adaptive-wakeup/sessions/${encodeURIComponent(sessionId)}/stop`, {
        method: 'POST',
      });
      if (res.ok) {
        const data: WakeupBudgetStatus = await res.json();
        setStatus(data);
      }
      onStopWakeup?.(sessionId);
    } catch {
      setStatus((prev) => ({
        ...prev,
        is_user_stopped: true,
      }));
      onStopWakeup?.(sessionId);
    } finally {
      setLoading(false);
    }
  };

  const isDegraded = status.is_exhausted || activeChannel === 'degrade';
  const isStopped = status.is_user_stopped || activeChannel === 'suppress';
  const isInject = activeChannel === 'inject';

  return (
    <section
      aria-label="Adaptive Wakeup Supervision"
      className={`rounded-lg border px-3 py-2.5 my-2 text-xs shadow-sm transition-all ${
        isStopped
          ? 'border-gray-700 bg-gray-900/60 text-gray-300'
          : isDegraded
            ? 'border-amber-600/60 bg-amber-950/40 text-amber-200'
            : isInject
              ? 'border-cyan-600/60 bg-cyan-950/40 text-cyan-200'
              : 'border-blue-600/60 bg-blue-950/40 text-blue-200'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 font-medium">
          {isStopped ? (
            <ShieldAlert className="w-4 h-4 text-gray-400" />
          ) : isDegraded ? (
            <AlertTriangle className="w-4 h-4 text-amber-400" />
          ) : isInject ? (
            <Cpu className="w-4 h-4 text-cyan-400" />
          ) : (
            <Play className="w-4 h-4 text-blue-400 animate-pulse" />
          )}

          <span>
            {isStopped
              ? '自动唤醒已抑制 (用户中止)'
              : isDegraded
                ? `连续自唤醒熔断保护 (${status.consecutive_wakes}/${status.max_consecutive_wakes})`
                : isInject
                  ? '并发任务步骤合并 (宿主忙碌中)'
                  : `自适应续跑进行中 (${status.consecutive_wakes}/${status.max_consecutive_wakes})`}
          </span>

          <span
            className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-semibold tracking-wider ${
              isStopped
                ? 'bg-gray-800 text-gray-300'
                : isDegraded
                  ? 'bg-amber-900/80 text-amber-300 border border-amber-700/50'
                  : isInject
                    ? 'bg-cyan-900/80 text-cyan-300 border border-cyan-700/50'
                    : 'bg-blue-900/80 text-blue-300 border border-blue-700/50'
            }`}
          >
            {sourceType === 'subagent' ? 'Subagent' : 'Background Job'}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {isDegraded && (
            <button
              type="button"
              onClick={() => void handleReset()}
              disabled={loading}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-700 hover:bg-amber-600 text-white font-medium text-[11px] transition-colors disabled:opacity-50"
            >
              <RotateCcw className="w-3 h-3" />
              重置预算
            </button>
          )}

          {!isStopped && !isDegraded && (
            <button
              type="button"
              onClick={() => void handleStop()}
              disabled={loading}
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-red-900/60 hover:bg-red-800 text-red-200 text-[11px] border border-red-700/40 transition-colors disabled:opacity-50"
            >
              <Pause className="w-3 h-3" />
              停止续跑
            </button>
          )}

          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              className="px-1 text-gray-400 hover:text-gray-200 transition-colors ml-1"
              aria-label="关闭指示卡片"
            >
              ×
            </button>
          )}
        </div>
      </div>

      {sourceSummary && (
        <div className="mt-1.5 pt-1.5 border-t border-current/10 text-[11px] opacity-90 flex items-start gap-1">
          <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 opacity-70" />
          <span className="truncate">{sourceSummary}</span>
        </div>
      )}

      {isDegraded && (
        <div className="mt-1 text-[11px] text-amber-300/90 font-sans">
          已达连续自动唤醒上限(3轮)，防止无人类介入的失控循环。发送新消息即可接续并重置配额。
        </div>
      )}
    </section>
  );
};

export default AdaptiveWakeupIndicator;
