/**
 * [INPUT]: SandboxHardwareTelemetryDashboardProps with hardware telemetry snapshot and breaker controls.
 * [OUTPUT]: SandboxHardwareTelemetryDashboard React component visualizing multi-tier runaway circuit breaking and sandbox metrics.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/SandboxHardwareTelemetryDashboard.tsx
 */

import React, { useState } from 'react';
import {
  CircuitBreakerEvaluationItem,
  CircuitBreakerLevelType,
  SandboxHardwareTelemetryDashboardProps,
} from './sandboxHardwareTelemetryTypes';

export const SandboxHardwareTelemetryDashboard: React.FC<SandboxHardwareTelemetryDashboardProps> = ({
  snapshot,
  onRefresh,
  onResetBreaker,
  onUpdateThresholds,
  isRefreshing = false,
}) => {
  const [warningCpu, setWarningCpu] = useState<number>(snapshot.config.warning_cpu_threshold);
  const [suspendCpu, setSuspendCpu] = useState<number>(snapshot.config.suspend_cpu_threshold);
  const [tripCpu, setTripCpu] = useState<number>(snapshot.config.trip_cpu_threshold);
  const [isSavingConfig, setIsSavingConfig] = useState<boolean>(false);

  const sample = snapshot.latest_sample;

  const getLevelBanner = (level: CircuitBreakerLevelType) => {
    switch (level) {
      case 'tripped':
        return {
          title: '🔴 红色硬熔断已触发 (TRIPPED)',
          desc: '沙箱资源持续严重超标，失控死循环进程组已优雅终止并回收句柄，请检查事故日志',
          cls: 'border-rose-500/60 bg-rose-950/40 text-rose-300',
        };
      case 'suspended':
        return {
          title: '🟠 橙色保护挂起中 (SUSPENDED)',
          desc: '资源使用率触及 90% 阶梯阈值，智能体执行已自动冻结，等待用户确认或手动干预',
          cls: 'border-amber-500/60 bg-amber-950/40 text-amber-300',
        };
      case 'warning':
        return {
          title: '🟡 黄色资源预警 (WARNING)',
          desc: '检测到 CPU/内存激增斜率或超过 80% 警戒线，已向控制台推送性能损耗提示',
          cls: 'border-yellow-500/60 bg-yellow-950/40 text-yellow-300',
        };
      case 'normal':
      default:
        return {
          title: '🟢 绿色安全放行 (NORMAL)',
          desc: '硬件各项物理水位正常稳定，无失控死循环隐患，长程任务受三级阶梯熔断保护',
          cls: 'border-emerald-500/60 bg-emerald-950/40 text-emerald-300',
        };
    }
  };

  const handleSaveConfig = async () => {
    if (!onUpdateThresholds || isSavingConfig) return;
    try {
      setIsSavingConfig(true);
      await onUpdateThresholds({
        warning_cpu_threshold: warningCpu,
        suspend_cpu_threshold: suspendCpu,
        trip_cpu_threshold: tripCpu,
      });
    } finally {
      setIsSavingConfig(false);
    }
  };

  const levelInfo = getLevelBanner(snapshot.current_level);

  return (
    <div className="flex flex-col space-y-6 rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-xl">
      {/* 头部标题与控制栏 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center space-x-3">
            <span className="text-xl font-bold tracking-tight text-white">
              沙箱硬件资源遥测与失控三级熔断控制台
            </span>
            <span className="rounded-full border border-sky-500/40 bg-sky-500/10 px-2.5 py-0.5 text-xs text-sky-300">
              安界信 × Qoder 运维控制面对齐
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            秒级动态采集沙箱底层物理硬件度量（CPU/RAM/Disk/Network），防范死循环打满 CPU 与 OOM 瘫痪宿主机
          </p>
        </div>
        <div className="flex items-center space-x-3">
          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={isRefreshing}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
            >
              {isRefreshing ? '刷新中...' : '刷新度量'}
            </button>
          )}
          {onResetBreaker && (
            <button
              onClick={() => {
                void onResetBreaker();
              }}
              className="rounded-lg border border-emerald-900/60 bg-emerald-950/40 px-3 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-900/60"
            >
              复位恢复熔断
            </button>
          )}
        </div>
      </div>

      {/* 三级阶梯熔断状态横幅 */}
      <div className={`rounded-xl border p-4 ${levelInfo.cls}`}>
        <div className="flex items-center justify-between">
          <div className="font-bold text-sm tracking-wide">{levelInfo.title}</div>
          <div className="text-xs font-mono opacity-80">
            连续违规计数: {snapshot.consecutive_violations} / {snapshot.config.max_consecutive_violations}
          </div>
        </div>
        <p className="mt-1 text-xs opacity-90">{levelInfo.desc}</p>
      </div>

      {/* 4 大核心硬件指标卡 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* 卡片 1: CPU 核心使用率 */}
        <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/50 p-4 space-y-2">
          <div className="text-xs font-medium text-zinc-400">CPU 核心使用率 (Peak)</div>
          <div className="text-2xl font-bold text-white">
            {sample ? `${sample.cpu_percent.toFixed(1)}%` : '—'}
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
            <div
              className={`h-full ${
                (sample?.cpu_percent || 0) >= 90
                  ? 'bg-rose-500'
                  : (sample?.cpu_percent || 0) >= 80
                  ? 'bg-amber-500'
                  : 'bg-sky-500'
              }`}
              style={{ width: `${Math.min(100, sample?.cpu_percent || 0)}%` }}
            />
          </div>
          <div className="text-[11px] text-zinc-500">
            预警: {snapshot.config.warning_cpu_threshold}% | 挂起: {snapshot.config.suspend_cpu_threshold}% | 熔断: {snapshot.config.trip_cpu_threshold}%
          </div>
        </div>

        {/* 卡片 2: 物理内存驻留 (RSS) */}
        <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/50 p-4 space-y-2">
          <div className="text-xs font-medium text-zinc-400">物理内存占用 (RAM RSS)</div>
          <div className="text-2xl font-bold text-white">
            {sample ? `${sample.memory_percent.toFixed(1)}%` : '—'}
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
            <div
              className={`h-full ${
                (sample?.memory_percent || 0) >= 90
                  ? 'bg-rose-500'
                  : (sample?.memory_percent || 0) >= 80
                  ? 'bg-amber-500'
                  : 'bg-emerald-500'
              }`}
              style={{ width: `${Math.min(100, sample?.memory_percent || 0)}%` }}
            />
          </div>
          <div className="text-[11px] text-zinc-500">
            {sample
              ? `${(sample.memory_used_bytes / (1024 * 1024 * 1024)).toFixed(1)} GB / ${(sample.memory_total_bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
              : '—'}
          </div>
        </div>

        {/* 卡片 3: 工作区磁盘 Volume */}
        <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/50 p-4 space-y-2">
          <div className="text-xs font-medium text-zinc-400">沙箱磁盘 Volume 占用</div>
          <div className="text-2xl font-bold text-white">
            {sample ? `${sample.disk_percent.toFixed(1)}%` : '—'}
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
            <div
              className="h-full bg-indigo-500"
              style={{ width: `${Math.min(100, sample?.disk_percent || 0)}%` }}
            />
          </div>
          <div className="text-[11px] text-zinc-500">
            {sample
              ? `${(sample.disk_used_bytes / (1024 * 1024 * 1024)).toFixed(1)} GB / ${(sample.disk_total_bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
              : '—'}
          </div>
        </div>

        {/* 卡片 4: 任务生命周期保护配额 */}
        <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/50 p-4 space-y-2">
          <div className="text-xs font-medium text-zinc-400">单任务安全时间上限</div>
          <div className="text-2xl font-bold text-purple-300">
            {Math.round(snapshot.config.max_task_duration_seconds / 60)} 分钟
          </div>
          <div className="text-xs text-zinc-400">连续违规容忍: {snapshot.config.max_consecutive_violations} 次</div>
          <div className="text-[11px] text-zinc-500">超过上限自动触发进程组回收</div>
        </div>
      </div>

      {/* 运维阈值配置控制台 */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-zinc-200">
            阶梯熔断阈值微调控制台 (Threshold Tuner)
          </h3>
          {onUpdateThresholds && (
            <button
              onClick={() => {
                void handleSaveConfig();
              }}
              disabled={isSavingConfig}
              className="rounded-lg border border-sky-800 bg-sky-950/40 px-3 py-1.5 text-xs font-medium text-sky-300 hover:bg-sky-900/60 disabled:opacity-50"
            >
              {isSavingConfig ? '保存中...' : '应用新阈值'}
            </button>
          )}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div className="space-y-1">
            <label className="text-zinc-400">Level 1 预警 CPU 阈值 (%)</label>
            <input
              type="number"
              value={warningCpu}
              onChange={(e) => setWarningCpu(Number(e.target.value))}
              className="w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-zinc-200 outline-none"
              min={1}
              max={100}
            />
          </div>
          <div className="space-y-1">
            <label className="text-zinc-400">Level 2 挂起 CPU 阈值 (%)</label>
            <input
              type="number"
              value={suspendCpu}
              onChange={(e) => setSuspendCpu(Number(e.target.value))}
              className="w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-zinc-200 outline-none"
              min={1}
              max={100}
            />
          </div>
          <div className="space-y-1">
            <label className="text-zinc-400">Level 3 硬熔断 CPU 阈值 (%)</label>
            <input
              type="number"
              value={tripCpu}
              onChange={(e) => setTripCpu(Number(e.target.value))}
              className="w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-zinc-200 outline-none"
              min={1}
              max={100}
            />
          </div>
        </div>
      </div>

      {/* 事故日志与违规事件流 */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold tracking-wide text-zinc-200">
          现场事故日志与违规事件流 (Incident History)
        </h3>
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-left text-xs text-zinc-300">
            <thead className="border-b border-zinc-800 bg-zinc-900/80 text-zinc-400">
              <tr>
                <th className="px-4 py-2.5 font-medium">安全阶梯</th>
                <th className="px-4 py-2.5 font-medium">触发指标</th>
                <th className="px-4 py-2.5 font-medium">实际值 vs 阈值</th>
                <th className="px-4 py-2.5 font-medium">自愈干预动作说明</th>
                <th className="px-4 py-2.5 font-medium">时间戳</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60 bg-zinc-950/40">
              {snapshot.incident_history.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-zinc-500">
                    暂无违规事故，沙箱运行平稳
                  </td>
                </tr>
              ) : (
                snapshot.incident_history.map((inc: CircuitBreakerEvaluationItem, idx: number) => (
                  <tr key={`${inc.evaluated_at_ms}-${idx}`} className="hover:bg-zinc-900/40">
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block rounded border px-2 py-0.5 text-xs font-semibold ${
                          inc.level === 'tripped'
                            ? 'border-rose-500/50 bg-rose-500/10 text-rose-400'
                            : inc.level === 'suspended'
                            ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                            : 'border-yellow-500/50 bg-yellow-500/10 text-yellow-400'
                        }`}
                      >
                        {inc.level.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-zinc-300">{inc.triggered_metric}</td>
                    <td className="px-4 py-3 font-mono text-zinc-200">
                      {inc.current_value.toFixed(1)}% (限 {inc.threshold_value.toFixed(1)}%)
                    </td>
                    <td className="px-4 py-3 text-zinc-300">{inc.action_description}</td>
                    <td className="px-4 py-3 text-zinc-500">
                      {new Date(inc.evaluated_at_ms).toLocaleTimeString()}
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
