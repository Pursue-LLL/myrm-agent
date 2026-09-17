'use client';

/**
 * [INPUT]
 * @/services/memory/cognitiveClock::(getCognitiveClockStatus, triggerT1SessionDebounce, CognitiveClockStatus)
 * lucide-react::(Activity, Clock, Layers, Moon, RefreshCw, ShieldCheck, Sparkles, Zap)
 *
 * [OUTPUT]
 * CognitiveClockPanel: Interactive dashboard for Hope/Nested Learning 4-tier cognitive clock.
 *
 * [POS]
 * Frontend Memory Command Center component. Visualizes T0-T3 cadences, cooperative
 * yielding state, and wakeup smoothing guard. Zero native emojis used.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  CheckCircle2,
  Clock,
  Layers,
  Moon,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Zap,
} from 'lucide-react';

import {
  getCognitiveClockStatus,
  triggerT1SessionDebounce,
  type CognitiveClockStatus,
} from '@/services/memory/cognitiveClock';
import { cn } from '@/lib/utils/classnameUtils';

interface CognitiveClockPanelProps {
  className?: string;
}

export const CognitiveClockPanel: React.FC<CognitiveClockPanelProps> = ({ className }) => {
  const [status, setStatus] = useState<CognitiveClockStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [t1Triggering, setT1Triggering] = useState<boolean>(false);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getCognitiveClockStatus();
      setStatus(data);
    } catch {
      // Graceful fallback on network or server error
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 15000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const handleManualRefresh = async () => {
    setRefreshing(true);
    await fetchStatus();
  };

  const handleManualT1 = async () => {
    setT1Triggering(true);
    try {
      await triggerT1SessionDebounce('manual-command-center');
      await fetchStatus();
    } finally {
      setT1Triggering(false);
    }
  };

  const cadences = [
    {
      id: 't0',
      tag: '实时工作台',
      title: '即时交互记忆',
      desc: '毫秒级捕获对话过程、工具输出与上下文即时状态',
      icon: Zap,
      status: '实时生效',
      statusColor: 'text-amber-500 bg-amber-500/10 border-amber-500/20',
      interval: '< 50ms',
    },
    {
      id: 't1',
      tag: '会话提炼',
      title: '会话偏好沉淀',
      desc: '对话结束后的智能知识提炼与交互习惯自动总结',
      icon: Layers,
      status: status?.user_activity_detected ? '前台避让中' : '就绪',
      statusColor: status?.user_activity_detected
        ? 'text-orange-500 bg-orange-500/10 border-orange-500/20'
        : 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20',
      interval: '防抖 15s',
    },
    {
      id: 't2',
      tag: '闲时守护',
      title: '记忆整合与固化',
      desc: '自动整理重复信息、归档过期记忆并生成安全健康快照',
      icon: Moon,
      status: status?.wakeup_grace_period_active
        ? '唤醒平滑保护'
        : status?.last_skip_reason === 'user_active'
          ? '打字避让中 (15m补跑)'
          : status?.within_quiet_window
            ? '静默守护运行中'
            : '等待空闲窗口',
      statusColor: status?.wakeup_grace_period_active
        ? 'text-indigo-500 bg-indigo-500/10 border-indigo-500/20'
        : status?.last_skip_reason === 'user_active'
          ? 'text-amber-500 bg-amber-500/10 border-amber-500/20'
          : status?.within_quiet_window
            ? 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20'
            : 'text-muted-foreground bg-muted/30 border-border/40',
      interval: `${status?.healthy_interval_hours ?? 6}h 周期`,
    },
    {
      id: 't3',
      tag: '周期演化',
      title: '深度认知自进化',
      desc: '跨周期的宏观使用模式发掘、深层思维习惯与技能沉淀',
      icon: Sparkles,
      status: '每周周期巡检',
      statusColor: 'text-purple-500 bg-purple-500/10 border-purple-500/20',
      interval: '168h 每周',
    },
  ];

  return (
    <div
      className={cn(
        'rounded-2xl border border-border/70 bg-card/80 p-5 shadow-xs backdrop-blur-xs transition-colors',
        className
      )}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-border/50">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary border border-primary/20">
            <Clock className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              嵌套学习多频认知时钟
              <span className="text-[10px] font-medium tracking-wide uppercase px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                Cognitive Continuum
              </span>
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              四层嵌套自进化的时间尺度调度，前台输入无感避让，设备唤醒平滑保护
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleManualT1}
            disabled={t1Triggering}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border/70 bg-background/80 px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent hover:text-accent-foreground disabled:opacity-50 transition-colors"
          >
            <Layers className={cn('h-3.5 w-3.5', t1Triggering && 'animate-spin')} />
            {t1Triggering ? '提炼中...' : '提炼当前会话'}
          </button>
          <button
            type="button"
            onClick={handleManualRefresh}
            disabled={refreshing || loading}
            aria-label="刷新时钟状态"
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border/70 bg-background/80 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 mt-4">
        {cadences.map((cadence) => {
          const Icon = cadence.icon;
          return (
            <div
              key={cadence.id}
              className="flex flex-col justify-between rounded-xl border border-border/60 bg-accent/20 p-3.5 hover:border-border transition-colors"
            >
              <div>
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    <Icon className="h-4 w-4 text-primary" />
                    <span className="text-xs font-semibold text-foreground tracking-tight">
                      {cadence.tag}
                    </span>
                  </div>
                  <span
                    className={cn(
                      'text-[10px] font-medium px-2 py-0.5 rounded-full border',
                      cadence.statusColor
                    )}
                  >
                    {cadence.status}
                  </span>
                </div>
                <div className="text-xs font-medium text-foreground">{cadence.title}</div>
                <p className="text-[11px] text-muted-foreground mt-1 line-clamp-2 leading-relaxed">
                  {cadence.desc}
                </p>
              </div>

              <div className="mt-3.5 pt-2.5 border-t border-border/40 flex items-center justify-between text-[11px] text-muted-foreground">
                <span className="flex items-center gap-1 font-mono">
                  <Clock className="h-3 w-3" />
                  {cadence.interval}
                </span>
                <span className="text-muted-foreground/80 font-mono text-[10px]">
                  {cadence.id === 't2' && status?.seconds_until_next !== null && status?.seconds_until_next !== undefined
                    ? `下次: ${Math.round(status.seconds_until_next / 60)}m`
                    : '自动调度'}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3 pt-3.5 border-t border-border/40">
        <div className="flex items-center gap-3 rounded-xl border border-border/50 bg-background/50 p-3">
          <div
            className={cn(
              'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border',
              status?.user_activity_detected
                ? 'bg-amber-500/10 border-amber-500/20 text-amber-500'
                : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500'
            )}
          >
            <Activity className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-medium text-foreground">前台输入协同避让</span>
              <span
                className={cn(
                  'text-[10px] px-1.5 py-0.2 rounded font-mono',
                  status?.user_activity_detected
                    ? 'text-amber-500 bg-amber-500/10'
                    : 'text-emerald-500 bg-emerald-500/10'
                )}
              >
                {status?.user_activity_detected ? '检测到输入中' : '常态就绪'}
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground truncate mt-0.5">
              打字或前台交互时，后台任务自动静默挂起并让步资源，杜绝界面卡顿
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 rounded-xl border border-border/50 bg-background/50 p-3">
          <div
            className={cn(
              'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border',
              status?.wakeup_grace_period_active
                ? 'bg-indigo-500/10 border-indigo-500/20 text-indigo-500'
                : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500'
            )}
          >
            <ShieldCheck className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-medium text-foreground">设备唤醒平滑保护</span>
              <span
                className={cn(
                  'text-[10px] px-1.5 py-0.2 rounded font-mono',
                  status?.wakeup_grace_period_active
                    ? 'text-indigo-500 bg-indigo-500/10'
                    : 'text-emerald-500 bg-emerald-500/10'
                )}
              >
                {status?.wakeup_grace_period_active ? '唤醒保护生效中' : '监控中'}
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground truncate mt-0.5">
              智能识别设备休眠恢复事件，平滑分流密集任务，避免唤醒瞬时系统负荷突增
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
