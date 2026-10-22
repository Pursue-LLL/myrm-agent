/**
 * [INPUT]: LoopForgeOtelOptionalDashboardProps with local sink status, captured span list, and toggle/refresh handlers.
 * [OUTPUT]: LoopForgeOtelOptionalDashboard component rendering offline local-disk telemetry fallback and trace visualizer.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/LoopForgeOtelOptionalDashboard.tsx
 */

import React, { useState } from 'react';
import { LoopForgeOtelOptionalDashboardProps } from './localSinkTypes';

export const LoopForgeOtelOptionalDashboard: React.FC<LoopForgeOtelOptionalDashboardProps> = ({
  status,
  spans,
  onToggleEnabled,
  onRefresh,
  onSimulateSpan,
}) => {
  const [toggleLoading, setToggleLoading] = useState<boolean>(false);
  const [simLoading, setSimLoading] = useState<boolean>(false);

  const handleToggle = async () => {
    if (!onToggleEnabled) return;
    setToggleLoading(true);
    try {
      await onToggleEnabled(!status.is_enabled);
    } finally {
      setToggleLoading(false);
    }
  };

  const handleSimulate = async () => {
    if (!onSimulateSpan) return;
    setSimLoading(true);
    try {
      await onSimulateSpan();
    } finally {
      setSimLoading(false);
    }
  };

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  return (
    <div className="flex flex-col space-y-6 rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-xl">
      {/* 头部摘要与操作 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center space-x-3">
            <span className="text-xl font-bold tracking-tight text-white">
              OpenTelemetry 缺失降级与本地盘兜底大盘 (LoopForge OTel Dashboard)
            </span>
            <span
              className={`rounded-md border px-2.5 py-0.5 font-mono text-xs font-semibold ${
                status.is_enabled
                  ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400'
                  : 'border-zinc-700 bg-zinc-900 text-zinc-400'
              }`}
            >
              {status.is_enabled ? '本地盘落盘兜底中 (Local Disk Active)' : '仅内存环形缓冲 (Memory Buffer)'}
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            缺远端 OTel 收集器时不崩溃，并提供 Opt-In 本地磁盘持久化，保障本地桌面端与单机离线调用链可溯源。
          </p>
        </div>

        <div className="flex items-center space-x-3">
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:border-zinc-500 hover:bg-zinc-800 transition"
            >
              刷新状态
            </button>
          )}
          {onSimulateSpan && (
            <button
              onClick={handleSimulate}
              disabled={simLoading}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 transition disabled:opacity-50"
            >
              {simLoading ? '模拟中...' : '模拟上报 Span'}
            </button>
          )}
          {onToggleEnabled && (
            <button
              onClick={handleToggle}
              disabled={toggleLoading}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                status.is_enabled
                  ? 'border border-amber-600 bg-amber-950/40 text-amber-300 hover:bg-amber-900/60'
                  : 'border border-emerald-600 bg-emerald-950/40 text-emerald-300 hover:bg-emerald-900/60'
              }`}
            >
              {toggleLoading
                ? '切换中...'
                : status.is_enabled
                ? '关闭本地落盘'
                : '开启本地落盘 (Opt-In)'}
            </button>
          )}
        </div>
      </div>

      {/* 核心指标卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="text-zinc-400">已落盘 Spans 总数</div>
          <div className="mt-1 font-mono text-xl font-bold text-white">
            {status.persisted_spans_count.toLocaleString()}
          </div>
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="text-zinc-400">内存缓冲 Spans</div>
          <div className="mt-1 font-mono text-xl font-bold text-sky-400">
            {status.buffered_spans_count.toLocaleString()}
          </div>
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="text-zinc-400">本地磁盘占用</div>
          <div className="mt-1 font-mono text-xl font-bold text-emerald-400">
            {formatBytes(status.file_size_bytes)}
          </div>
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="text-zinc-400">落盘状态</div>
          <div className="mt-1 font-mono text-sm font-semibold text-zinc-300">
            {status.is_enabled ? '持续追加写入 (Active)' : '已挂起 (Paused)'}
          </div>
        </div>
      </div>

      {/* 本地存储路径 */}
      <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-3 text-xs font-mono text-zinc-400 flex flex-wrap items-center justify-between gap-2">
        <div>
          <span>本地落盘路径: </span>
          <span className="text-zinc-200">{status.sink_path}</span>
        </div>
        {status.last_flush_iso && (
          <div className="text-zinc-500 text-[11px]">
            最近写入: {new Date(status.last_flush_iso).toLocaleTimeString()}
          </div>
        )}
      </div>

      {/* 链路 Spans 最近调用回放 */}
      <div>
        <div className="text-xs font-semibold text-zinc-300 mb-3 flex items-center justify-between">
          <span>最近捕获调用链 Spans 回放 ({spans.length} 条)</span>
          <span className="text-[11px] font-mono text-zinc-500">环形定长回放 (RingBuffer)</span>
        </div>

        {spans.length === 0 ? (
          <div className="flex h-32 flex-col items-center justify-center rounded-lg border border-dashed border-zinc-800 text-zinc-500 text-xs">
            暂无捕获的 Span 链路数据
          </div>
        ) : (
          <div className="space-y-2.5 max-h-80 overflow-y-auto pr-1">
            {spans.map((sp) => (
              <div
                key={`${sp.trace_id}-${sp.span_id}`}
                className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3 text-xs shadow-sm"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center space-x-2">
                    <span className="rounded bg-sky-950 border border-sky-800/60 px-1.5 py-0.5 font-mono text-[10px] text-sky-300">
                      {sp.status}
                    </span>
                    <span className="font-semibold text-white">{sp.name}</span>
                  </div>
                  <span className="font-mono text-zinc-400">{sp.duration_ms} ms</span>
                </div>

                <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-zinc-500">
                  <div>
                    Trace: <span className="text-zinc-400">{sp.trace_id}</span>
                  </div>
                  <div>
                    Span: <span className="text-zinc-400">{sp.span_id}</span>
                  </div>
                  <div>
                    时间: <span className="text-zinc-400">{new Date(sp.end_time_iso).toLocaleTimeString()}</span>
                  </div>
                </div>

                {sp.attributes && Object.keys(sp.attributes).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {Object.entries(sp.attributes).map(([k, v]) => (
                      <span
                        key={k}
                        className="rounded bg-zinc-950 px-2 py-0.5 font-mono text-[10px] text-zinc-400"
                      >
                        {k}: {v}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 底部隔离保障说明 */}
      <div className="rounded-lg border border-emerald-900/30 bg-emerald-950/20 px-3.5 py-2.5 text-xs text-emerald-400">
        <span className="font-semibold">零硬依赖与断点保障：</span>
        即使未安装 OpenTelemetry 官方 SDK 或网络隔离断开，本地盘 Sink 自动兜底将 Trace Spans 追加持久化至本地 JSONL 文件，确保单机开发环境与桌面端可观测性 100% 完整闭环。
      </div>
    </div>
  );
};
