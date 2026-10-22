/**
 * [INPUT]: MemoryBackendMetricsReportItem, toggle and reset callbacks.
 * [OUTPUT]: MemoryBackendMetricsDashboard component comparing latencies across backends and recall phases.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/MemoryBackendMetricsDashboard.tsx
 */

import React, { useState } from 'react';
import {
  MemoryBackendKindType,
  MemoryBackendMetricsDashboardProps,
  MemoryBackendPerformanceStatsItem,
  MemoryOperationType,
  RecallPhaseType,
} from './memoryBackendMetricsTypes';

export const MemoryBackendMetricsDashboard: React.FC<MemoryBackendMetricsDashboardProps> = ({
  report,
  onToggleOptIn,
  onReset,
  className = '',
}) => {
  const [selectedBackend, setSelectedBackend] = useState<string>('all');
  const [selectedPhase, setSelectedPhase] = useState<string>('all');

  const getBackendBadge = (backend: MemoryBackendKindType) => {
    switch (backend) {
      case 'sqlite_fts5':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
            SQLite FTS5
          </span>
        );
      case 'qdrant':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
            Qdrant Vector
          </span>
        );
      case 'in_memory':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30">
            In-Memory
          </span>
        );
      case 'external':
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30">
            External
          </span>
        );
    }
  };

  const getPhaseBadge = (phase: RecallPhaseType) => {
    switch (phase) {
      case 'collect':
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-400 border border-blue-500/30">
            COLLECT
          </span>
        );
      case 'fuse':
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
            FUSE
          </span>
        );
      case 'rerank':
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
            RERANK
          </span>
        );
      case 'none':
      default:
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] text-zinc-500 border border-zinc-700/50">
            GENERAL
          </span>
        );
    }
  };

  const filteredStats = report.backend_stats.filter((stat: MemoryBackendPerformanceStatsItem) => {
    const matchBackend = selectedBackend === 'all' || stat.backend === selectedBackend;
    const matchPhase = selectedPhase === 'all' || stat.phase === selectedPhase;
    return matchBackend && matchPhase;
  });

  const totalDegraded = report.backend_stats.reduce((acc, curr) => acc + curr.degraded_count, 0);
  const activeBackendsCount = new Set(report.backend_stats.map((s) => s.backend)).size;

  return (
    <div
      data-testid="memory-backend-metrics-dashboard"
      className={`w-full bg-zinc-950 text-zinc-100 border border-zinc-800 rounded-xl p-5 shadow-2xl space-y-5 font-mono ${className}`}
    >
      {/* Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <h2 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
            <span>🧠</span>
            <span>Memory Backend Telemetry &amp; Phase Breakdown</span>
          </h2>
          <p className="text-xs text-zinc-400 mt-1">
            Opt-in label dimensions comparing P50/P95 latencies across SQLite FTS5, Qdrant, and In-Memory pipelines.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {onToggleOptIn && (
            <button
              data-testid="toggle-opt-in-btn"
              onClick={() => onToggleOptIn(!report.opt_in_enabled)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                report.opt_in_enabled
                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 hover:bg-emerald-500/30'
                  : 'bg-zinc-800 text-zinc-400 border-zinc-700 hover:bg-zinc-700'
              }`}
            >
              {report.opt_in_enabled ? 'Opt-in Label: Enabled' : 'Opt-in Label: Disabled'}
            </button>
          )}

          {onReset && (
            <button
              data-testid="reset-metrics-btn"
              onClick={onReset}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/40 hover:bg-rose-500/30 transition-all"
            >
              Reset Metrics
            </button>
          )}
        </div>
      </div>

      {/* Top Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <span className="text-[11px] text-zinc-400 block">Total Telemetry Samples</span>
          <span data-testid="total-samples-val" className="text-2xl font-bold text-zinc-100">
            {report.total_samples}
          </span>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <span className="text-[11px] text-zinc-400 block">Active Backends Monitored</span>
          <span data-testid="active-backends-val" className="text-2xl font-bold text-cyan-400">
            {activeBackendsCount}
          </span>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <span className="text-[11px] text-zinc-400 block">Degraded / Fallback Operations</span>
          <span
            data-testid="degraded-count-val"
            className={`text-2xl font-bold ${totalDegraded > 0 ? 'text-amber-400' : 'text-emerald-400'}`}
          >
            {totalDegraded}
          </span>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs bg-zinc-900/50 p-2 rounded-lg border border-zinc-800/60">
        <div className="flex items-center gap-1">
          <span className="text-zinc-500 mr-2">Backend:</span>
          {['all', 'sqlite_fts5', 'qdrant', 'in_memory'].map((b) => (
            <button
              key={b}
              onClick={() => setSelectedBackend(b)}
              className={`px-2.5 py-1 rounded transition-colors ${
                selectedBackend === b
                  ? 'bg-zinc-700 text-zinc-100 font-bold'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {b.toUpperCase()}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1">
          <span className="text-zinc-500 mr-2">Phase:</span>
          {['all', 'collect', 'fuse', 'rerank'].map((p) => (
            <button
              key={p}
              onClick={() => setSelectedPhase(p)}
              className={`px-2.5 py-1 rounded transition-colors ${
                selectedPhase === p
                  ? 'bg-zinc-700 text-zinc-100 font-bold'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {p.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Metrics Table */}
      <div className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-900/40">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-zinc-800 bg-zinc-900/80 text-zinc-400 uppercase text-[10px]">
              <th className="py-2.5 px-3">Backend</th>
              <th className="py-2.5 px-3">Operation</th>
              <th className="py-2.5 px-3">Phase</th>
              <th className="py-2.5 px-3 text-right">Ops Count</th>
              <th className="py-2.5 px-3 text-right">Success Rate</th>
              <th className="py-2.5 px-3 text-right">Degraded</th>
              <th className="py-2.5 px-3 text-right">Avg (ms)</th>
              <th className="py-2.5 px-3 text-right">P50 (ms)</th>
              <th className="py-2.5 px-3 text-right">P95 (ms)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {filteredStats.length === 0 ? (
              <tr>
                <td colSpan={9} className="py-6 text-center text-zinc-500">
                  No memory operation telemetry recorded for this filter.
                </td>
              </tr>
            ) : (
              filteredStats.map((stat, idx) => (
                <tr
                  key={`${stat.backend}-${stat.operation}-${stat.phase}-${idx}`}
                  data-testid={`stat-row-${stat.backend}-${stat.phase}`}
                  className="hover:bg-zinc-800/40 transition-colors"
                >
                  <td className="py-2.5 px-3 whitespace-nowrap">{getBackendBadge(stat.backend)}</td>
                  <td className="py-2.5 px-3 text-zinc-300 font-medium uppercase text-[11px]">
                    {stat.operation}
                  </td>
                  <td className="py-2.5 px-3 whitespace-nowrap">{getPhaseBadge(stat.phase)}</td>
                  <td className="py-2.5 px-3 text-right text-zinc-200">{stat.total_operations}</td>
                  <td className="py-2.5 px-3 text-right">
                    <span
                      className={`font-semibold ${
                        stat.success_rate >= 0.99
                          ? 'text-emerald-400'
                          : stat.success_rate >= 0.9
                          ? 'text-amber-400'
                          : 'text-rose-400'
                      }`}
                    >
                      {(stat.success_rate * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-right">
                    {stat.degraded_count > 0 ? (
                      <span className="text-amber-400 font-bold">{stat.degraded_count}</span>
                    ) : (
                      <span className="text-zinc-500">0</span>
                    )}
                  </td>
                  <td className="py-2.5 px-3 text-right text-zinc-300">{stat.avg_duration_ms.toFixed(1)}</td>
                  <td className="py-2.5 px-3 text-right font-medium text-blue-300">
                    {stat.p50_duration_ms.toFixed(1)}
                  </td>
                  <td className="py-2.5 px-3 text-right font-semibold text-rose-300">
                    {stat.p95_duration_ms.toFixed(1)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
