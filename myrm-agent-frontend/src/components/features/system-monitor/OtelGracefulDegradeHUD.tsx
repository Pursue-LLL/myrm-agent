/**
 * [INPUT]: OtelGracefulDegradeHUDProps with degrade status, active probe, and simulation toggle callbacks.
 * [OUTPUT]: OtelGracefulDegradeHUD React component visualizing zero hard-dependency guarantees and NoOp fallbacks.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/OtelGracefulDegradeHUD.tsx
 */

import React, { useState } from 'react';
import {
  OtelGracefulDegradeHUDProps,
  OtelPostureState,
} from './otelDegradeTypes';

const STATE_CONFIG: Record<
  OtelPostureState,
  { label: string; bg: string; text: string; border: string; desc: string }
> = {
  ACTIVE: {
    label: '全量 OTel 追踪中 (Active)',
    bg: 'bg-emerald-500/10',
    text: 'text-emerald-400',
    border: 'border-emerald-500/30',
    desc: '环境已安装 OpenTelemetry 官方依赖，调用链与指标全量捕获中。',
  },
  DEGRADED_NO_OP: {
    label: '已优雅降级空跑 (Degraded No-Op) · 业务零中断',
    bg: 'bg-amber-500/10',
    text: 'text-amber-400',
    border: 'border-amber-500/30',
    desc: '环境中未安装 opentelemetry 库，探针已自动静默降级为 No-Op，业务执行 100% 正常。',
  },
  DISABLED: {
    label: '已配置禁用 (Disabled)',
    bg: 'bg-zinc-500/10',
    text: 'text-zinc-400',
    border: 'border-zinc-500/30',
    desc: '已通过 MYRM_DISABLE_OTEL 环境变量显式关闭追踪，探针已静默挂起。',
  },
};

export const OtelGracefulDegradeHUD: React.FC<OtelGracefulDegradeHUDProps> = ({
  status,
  onProbe,
  onSimulateMissingToggle,
  isSimulating = false,
}) => {
  const [toggleLoading, setToggleLoading] = useState<boolean>(false);
  const stateMeta = STATE_CONFIG[status.state];

  const handleToggleSimulation = async () => {
    if (!onSimulateMissingToggle) return;
    setToggleLoading(true);
    try {
      const willSimulate = status.state !== 'DEGRADED_NO_OP';
      await onSimulateMissingToggle(willSimulate);
    } finally {
      setToggleLoading(false);
    }
  };

  return (
    <div className="flex flex-col space-y-6 rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-xl">
      {/* 头部摘要 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center space-x-3">
            <span className="text-xl font-bold tracking-tight text-white">
              OpenTelemetry 探针零硬依赖与优雅降级 HUD
            </span>
            <span
              className={`rounded-md border px-2.5 py-0.5 font-mono text-xs font-medium ${stateMeta.bg} ${stateMeta.text} ${stateMeta.border}`}
            >
              {stateMeta.label}
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            {stateMeta.desc}
          </p>
        </div>

        <div className="flex items-center space-x-3">
          {onProbe && (
            <button
              onClick={onProbe}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:border-zinc-500 hover:bg-zinc-800 transition"
            >
              主动自检 (Probe)
            </button>
          )}
          {onSimulateMissingToggle && (
            <button
              onClick={handleToggleSimulation}
              disabled={toggleLoading || isSimulating}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                status.state === 'DEGRADED_NO_OP'
                  ? 'border border-emerald-600 bg-emerald-950/40 text-emerald-300 hover:bg-emerald-900/60'
                  : 'border border-amber-600 bg-amber-950/40 text-amber-300 hover:bg-amber-900/60'
              }`}
            >
              {toggleLoading
                ? '切换中...'
                : status.state === 'DEGRADED_NO_OP'
                ? '还原依赖 (Restore OTel)'
                : '模拟依赖缺失 (Simulate Missing)'}
            </button>
          )}
        </div>
      </div>

      {/* 3 大核心体征网格 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {/* 依赖安装状态 */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="text-xs text-zinc-400">环境依赖 (opentelemetry-api)</div>
          <div className="mt-2 flex items-center space-x-2">
            <span
              className={`inline-block h-2.5 w-2.5 rounded-full ${
                status.is_otel_installed ? 'bg-emerald-400' : 'bg-amber-400'
              }`}
            />
            <span className="text-base font-bold text-white font-mono">
              {status.is_otel_installed ? '已检测到依赖包' : '依赖缺失 · 安全隔离中'}
            </span>
          </div>
          <p className="mt-2 text-[11px] text-zinc-400">
            探针支持多 IDE 与裁剪沙箱零报错加载
          </p>
        </div>

        {/* 拦截保护 Span 计数 */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="flex items-center justify-between text-xs text-zinc-400">
            <span>已拦截 Span 调用</span>
            <span className="text-[10px] text-cyan-400">零开销穿透</span>
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-2xl font-bold tracking-tight text-white font-mono">
              {status.intercepted_spans_count}
            </span>
            <span className="text-xs text-zinc-400">次 Span 降级</span>
          </div>
          <p className="mt-2 text-[11px] text-zinc-400">
            上下文管理器与异常向上透传 100% 正常
          </p>
        </div>

        {/* 拦截保护 Metric 计数 */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="flex items-center justify-between text-xs text-zinc-400">
            <span>已拦截 Metric 打点</span>
            <span className="text-[10px] text-cyan-400">无缝吸收</span>
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-2xl font-bold tracking-tight text-white font-mono">
              {status.intercepted_metrics_count}
            </span>
            <span className="text-xs text-zinc-400">次指标打点</span>
          </div>
          <p className="mt-2 text-[11px] text-zinc-400">
            Counter/Histogram 零异常抛出
          </p>
        </div>
      </div>

      {/* 降级根因说明与零硬依赖铁律卡片 */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
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
                d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
              />
            </svg>
          </div>
          <div>
            <h5 className="text-xs font-semibold text-zinc-200">
              架构可靠性铁律：可观测性绝不能成为系统故障源 (Observability Zero Hard-Dependency)
            </h5>
            <p className="mt-1 text-xs text-zinc-400 leading-relaxed">
              当智能体运行于精简容器、本地命令行、或未安装全量 APM 依赖的沙箱环境时，若探针因缺失库抛出{' '}
              <code className="text-rose-300 font-mono">ModuleNotFoundError</code> 将直接中断业务。Myrm 采用优雅降级运行时（GracefulOtelRuntime），在缺失依赖时静默注入 NoOpSpan 与 NoOpMeter，保证一切核心执行流程顺畅无阻。
            </p>
            {status.degrade_reason && (
              <div className="mt-2 rounded border border-amber-500/30 bg-amber-950/20 px-3 py-1.5 text-xs text-amber-200 font-mono">
                当前降级原因: {status.degrade_reason}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 底部时间戳 */}
      <div className="flex justify-between text-[11px] text-zinc-500 border-t border-zinc-800/80 pt-3">
        <span>上次自检时间: {new Date(status.last_probe_time).toLocaleString()}</span>
        <span>Myrm Agent Harness Observability Shield v1.0</span>
      </div>
    </div>
  );
};
