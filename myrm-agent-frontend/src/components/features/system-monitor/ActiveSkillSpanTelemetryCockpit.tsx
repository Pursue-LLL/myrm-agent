/**
 * [INPUT]: ActiveSkillTelemetryReportItem, SkillSpanRecordItem array, callbacks.
 * [OUTPUT]: High-density industrial ActiveSkillSpanTelemetryCockpit component correlating OpenTelemetry spans with active skills.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/ActiveSkillSpanTelemetryCockpit.tsx
 */

import React, { useState } from 'react';
import {
  ActiveSkillSpanTelemetryCockpitProps,
  SkillSpanRecordItem,
  SkillTelemetryAggregationItem,
} from './activeSkillTelemetryTypes';

export const ActiveSkillSpanTelemetryCockpit: React.FC<ActiveSkillSpanTelemetryCockpitProps> = ({
  report,
  spans = [],
  onRefresh,
  onReset,
  className = '',
}) => {
  const [selectedSkill, setSelectedSkill] = useState<string>('all');

  const totalErrors = report.skill_aggregations.reduce((acc, curr) => acc + curr.error_spans, 0);

  const filteredSpans = spans.filter((span: SkillSpanRecordItem) => {
    if (selectedSkill === 'all') return true;
    if (selectedSkill === 'unattributed') return !span.active_skill;
    return span.active_skill === selectedSkill;
  });

  return (
    <div
      data-testid="active-skill-cockpit"
      className={`w-full bg-zinc-950 text-zinc-100 border border-zinc-800 rounded-xl p-5 shadow-2xl space-y-5 font-mono ${className}`}
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <h2 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
            <span>⚡</span>
            <span>Active Skill Span Telemetry &amp; Attribution Cockpit</span>
          </h2>
          <p className="text-xs text-zinc-400 mt-1">
            End-to-end ContextVar propagation injecting <code>myrm.skill.active</code> attributes across all child model and tool spans.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            ContextVar Span Processor Active
          </span>

          {onRefresh && (
            <button
              data-testid="refresh-telemetry-btn"
              onClick={onRefresh}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-zinc-800 text-zinc-300 border border-zinc-700 hover:bg-zinc-700 transition-all"
            >
              Refresh
            </button>
          )}

          {onReset && (
            <button
              data-testid="reset-telemetry-btn"
              onClick={onReset}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/40 hover:bg-rose-500/30 transition-all"
            >
              Reset
            </button>
          )}
        </div>
      </div>

      {/* Aggregate Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <span className="text-[11px] text-zinc-400 block">Total Spans Recorded</span>
          <span data-testid="total-spans-val" className="text-2xl font-bold text-zinc-100">
            {report.total_spans_recorded}
          </span>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <span className="text-[11px] text-zinc-400 block">Active Monitored Skills</span>
          <span data-testid="active-skills-val" className="text-2xl font-bold text-cyan-400">
            {report.skills_count}
          </span>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <span className="text-[11px] text-zinc-400 block">Unattributed Baseline Spans</span>
          <span data-testid="unattributed-spans-val" className="text-2xl font-bold text-zinc-400">
            {report.unattributed_spans_count}
          </span>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <span className="text-[11px] text-zinc-400 block">Skill Execution Errors</span>
          <span
            data-testid="total-errors-val"
            className={`text-2xl font-bold ${totalErrors > 0 ? 'text-rose-400' : 'text-emerald-400'}`}
          >
            {totalErrors}
          </span>
        </div>
      </div>

      {/* Skill Performance Aggregations Table */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs text-zinc-400">
          <span className="font-semibold uppercase tracking-wider text-[11px] text-zinc-300">
            Skill Aggregation &amp; P95 Latency Breakdown
          </span>
          <span>{report.skill_aggregations.length} Active Skills</span>
        </div>

        <div className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-900/40">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-zinc-800 bg-zinc-900/80 text-zinc-400 uppercase text-[10px]">
                <th className="py-2.5 px-3">Active Skill Name</th>
                <th className="py-2.5 px-3 text-right">Total Spans</th>
                <th className="py-2.5 px-3 text-right">Error Spans</th>
                <th className="py-2.5 px-3 text-right">Error Rate</th>
                <th className="py-2.5 px-3 text-right">Avg Duration (ms)</th>
                <th className="py-2.5 px-3 text-right">P95 Duration (ms)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {report.skill_aggregations.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-zinc-500">
                    No active skill spans recorded yet.
                  </td>
                </tr>
              ) : (
                report.skill_aggregations.map((agg: SkillTelemetryAggregationItem) => (
                  <tr
                    key={agg.skill_name}
                    data-testid={`skill-agg-row-${agg.skill_name}`}
                    className="hover:bg-zinc-800/40 transition-colors"
                  >
                    <td className="py-2.5 px-3 whitespace-nowrap">
                      <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                        {agg.skill_name}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right text-zinc-200">{agg.total_spans}</td>
                    <td className="py-2.5 px-3 text-right">
                      {agg.error_spans > 0 ? (
                        <span className="text-rose-400 font-bold">{agg.error_spans}</span>
                      ) : (
                        <span className="text-zinc-500">0</span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <span
                        className={`font-semibold ${
                          agg.error_rate === 0
                            ? 'text-emerald-400'
                            : agg.error_rate < 0.1
                            ? 'text-amber-400'
                            : 'text-rose-400'
                        }`}
                      >
                        {(agg.error_rate * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right text-zinc-300">
                      {agg.avg_duration_ms.toFixed(1)}
                    </td>
                    <td className="py-2.5 px-3 text-right font-semibold text-rose-300">
                      {agg.p95_duration_ms.toFixed(1)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Filter Tabs for Span Records */}
      {spans.length > 0 && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs bg-zinc-900/50 p-2 rounded-lg border border-zinc-800/60">
            <div className="flex items-center gap-1">
              <span className="text-zinc-500 mr-2">Filter Skill:</span>
              <button
                data-testid="filter-skill-all"
                onClick={() => setSelectedSkill('all')}
                className={`px-2.5 py-1 rounded transition-colors ${
                  selectedSkill === 'all'
                    ? 'bg-zinc-700 text-zinc-100 font-bold'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                ALL
              </button>
              {report.skill_aggregations.map((a) => (
                <button
                  key={a.skill_name}
                  data-testid={`filter-skill-${a.skill_name}`}
                  onClick={() => setSelectedSkill(a.skill_name)}
                  className={`px-2.5 py-1 rounded transition-colors ${
                    selectedSkill === a.skill_name
                      ? 'bg-zinc-700 text-zinc-100 font-bold'
                      : 'text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  {a.skill_name.toUpperCase()}
                </button>
              ))}
              <button
                data-testid="filter-skill-unattributed"
                onClick={() => setSelectedSkill('unattributed')}
                className={`px-2.5 py-1 rounded transition-colors ${
                  selectedSkill === 'unattributed'
                    ? 'bg-zinc-700 text-zinc-100 font-bold'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                UNATTRIBUTED
              </button>
            </div>
          </div>

          {/* Span Stream Table */}
          <div className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-900/40">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-900/80 text-zinc-400 uppercase text-[10px]">
                  <th className="py-2.5 px-3">Span Name</th>
                  <th className="py-2.5 px-3">Active Skill Tag</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3 text-right">Duration (ms)</th>
                  <th className="py-2.5 px-3">Trace / Span ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {filteredSpans.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-6 text-center text-zinc-500">
                      No spans match selected skill filter.
                    </td>
                  </tr>
                ) : (
                  filteredSpans.map((s) => (
                    <tr
                      key={s.span_id}
                      data-testid={`span-row-${s.span_id}`}
                      className="hover:bg-zinc-800/40 transition-colors"
                    >
                      <td className="py-2.5 px-3 font-semibold text-zinc-200">{s.name}</td>
                      <td className="py-2.5 px-3">
                        {s.active_skill ? (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                            {s.active_skill}
                          </span>
                        ) : (
                          <span className="text-zinc-500 text-[10px]">BASELINE (None)</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            s.status === 'ok'
                              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                              : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                          }`}
                        >
                          {s.status.toUpperCase()}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-right text-zinc-300">{s.duration_ms.toFixed(1)}</td>
                      <td className="py-2.5 px-3 text-[10px] text-zinc-500 font-mono">
                        {s.trace_id.slice(0, 8)}... / {s.span_id.slice(0, 8)}...
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
