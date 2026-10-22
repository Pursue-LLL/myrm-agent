/**
 * [INPUT]: GovernorLiveStatus list, QuotaPacingDecision results, and subagent drawer triggers.
 * [OUTPUT]: Heads-Up Display (HUD) rendering real-time RPM/TPM watermarks, zero-429 badges, and proactive shaping telemetry.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/RateLimitGovernorHUD.tsx
 */

import React, { useState } from 'react';
import type { GovernorLiveStatus, QuotaPacingDecision } from './rateLimitGovernorTypes';

export interface RateLimitGovernorHUDProps {
  statuses: GovernorLiveStatus[];
  latestDecision?: QuotaPacingDecision | null;
  onOpenSubagentDrawer?: () => void;
  onTriggerPreCheck?: (modelName: string, tokens: number) => void;
}

export const RateLimitGovernorHUD: React.FC<RateLimitGovernorHUDProps> = ({
  statuses,
  latestDecision,
  onOpenSubagentDrawer,
  onTriggerPreCheck,
}) => {
  const [selectedModel, setSelectedModel] = useState<string>('claude-3-5-sonnet');
  const [estimatedTokens, setEstimatedTokens] = useState<number>(2500);

  // Compute aggregate metrics
  const totalPrevented429 = statuses.reduce((acc, s) => acc + s.prevented_429_count, 0);
  const totalSmoothedRequests = statuses.reduce((acc, s) => acc + s.smoothed_request_count, 0);
  const activeSlicesCount = statuses.reduce((acc, s) => acc + s.active_subagent_slices_count, 0);

  const handleSimulateClick = () => {
    onTriggerPreCheck?.(selectedModel, estimatedTokens);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-5 text-slate-100">
      {/* Top Banner & Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl">⚡</span>
            <h2 className="text-base font-semibold text-white">客户端主动限流预测阀门与自适应配额调度</h2>
            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950 text-emerald-400 border border-emerald-700/60">
              Zero-429 Shield Active
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            动态嗅探上游响应头 · 60s 滑动窗口平滑微整形削峰 · 子 Agent 反贪婪切片隔离
          </p>
        </div>

        <div className="flex items-center gap-2">
          {onOpenSubagentDrawer && (
            <button
              type="button"
              onClick={onOpenSubagentDrawer}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-cyan-300 border border-slate-700 transition-colors flex items-center gap-1.5"
            >
              <span>🛡️</span>
              <span>子 Agent 切片配额</span>
            </button>
          )}
        </div>
      </div>

      {/* Aggregate KPI Badges */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="bg-slate-850/80 border border-slate-800 p-3.5 rounded-lg">
          <div className="text-[11px] font-medium text-slate-400">已消弭 429 撞墙风险</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-emerald-400">{totalPrevented429}</span>
            <span className="text-xs text-slate-500">次预判截流</span>
          </div>
        </div>

        <div className="bg-slate-850/80 border border-slate-800 p-3.5 rounded-lg">
          <div className="text-[11px] font-medium text-slate-400">350ms 微整形平流请求</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-cyan-400">{totalSmoothedRequests}</span>
            <span className="text-xs text-slate-500">次削峰放行</span>
          </div>
        </div>

        <div className="bg-slate-850/80 border border-slate-800 p-3.5 rounded-lg">
          <div className="text-[11px] font-medium text-slate-400">活跃隔离并发切片</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-indigo-400">{activeSlicesCount}</span>
            <span className="text-xs text-slate-500">个保护管道</span>
          </div>
        </div>
      </div>

      {/* Model Quota Watermarks Grid */}
      <div className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          多提供商模型配额水位遥测
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {statuses.map((item) => {
            const isHighWatermark = item.tpm_watermark_pct >= 85 || item.rpm_watermark_pct >= 85;
            return (
              <div
                key={item.model_name}
                className="bg-slate-800/50 border border-slate-700/60 rounded-lg p-3.5 space-y-3"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-semibold text-white">
                    {item.model_name}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                      isHighWatermark
                        ? 'bg-amber-950/60 text-amber-300 border-amber-700/80'
                        : 'bg-emerald-950/60 text-emerald-300 border-emerald-700/80'
                    }`}
                  >
                    {item.status_label}
                  </span>
                </div>

                {/* TPM Watermark */}
                <div className="space-y-1">
                  <div className="flex justify-between text-[11px] text-slate-400">
                    <span>TPM 水位</span>
                    <span className="font-mono text-slate-200">{item.tpm_watermark_pct}%</span>
                  </div>
                  <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                    <div
                      className={`h-full transition-all duration-300 ${
                        item.tpm_watermark_pct >= 85 ? 'bg-amber-400' : 'bg-emerald-400'
                      }`}
                      style={{ width: `${Math.min(100, item.tpm_watermark_pct)}%` }}
                    />
                  </div>
                </div>

                {/* RPM Watermark */}
                <div className="space-y-1">
                  <div className="flex justify-between text-[11px] text-slate-400">
                    <span>RPM 水位</span>
                    <span className="font-mono text-slate-200">{item.rpm_watermark_pct}%</span>
                  </div>
                  <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                    <div
                      className={`h-full transition-all duration-300 ${
                        item.rpm_watermark_pct >= 85 ? 'bg-amber-400' : 'bg-cyan-400'
                      }`}
                      style={{ width: `${Math.min(100, item.rpm_watermark_pct)}%` }}
                    />
                  </div>
                </div>

                <div className="text-[10px] text-slate-500 pt-1 border-t border-slate-700/40 flex justify-between">
                  <span>平流削峰: {item.smoothed_request_count}</span>
                  <span>避险: {item.prevented_429_count}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Interactive Simulation Console */}
      <div className="bg-slate-850/60 border border-slate-800 rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-300">
            🧪 客户端预测门禁即时推演
          </span>
          <span className="text-[11px] text-slate-500">零开销模拟评估</span>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-xs">
            <label htmlFor="model-select" className="text-slate-400">
              目标模型:
            </label>
            <select
              id="model-select"
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="bg-slate-800 border border-slate-700 text-xs text-white rounded px-2.5 py-1"
            >
              {statuses.map((s) => (
                <option key={s.model_name} value={s.model_name}>
                  {s.model_name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2 text-xs">
            <label htmlFor="token-input" className="text-slate-400">
              预计 Prompt Tokens:
            </label>
            <input
              id="token-input"
              type="number"
              value={estimatedTokens}
              onChange={(e) => setEstimatedTokens(Number(e.target.value))}
              className="w-24 bg-slate-800 border border-slate-700 text-xs text-white rounded px-2 py-1 font-mono"
            />
          </div>

          <button
            type="button"
            onClick={handleSimulateClick}
            className="px-3.5 py-1 text-xs font-medium rounded bg-cyan-600 hover:bg-cyan-500 text-white transition-colors"
          >
            执行前置预检
          </button>
        </div>

        {/* Latest Pre-Check Decision Output */}
        {latestDecision && (
          <div className="mt-3 p-3 rounded-lg bg-slate-900 border border-slate-700/80 text-xs space-y-1.5">
            <div className="flex items-center justify-between font-mono">
              <span className="text-slate-400">决策动作:</span>
              <span
                className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                  latestDecision.action === 'IMMEDIATE_PASS'
                    ? 'bg-emerald-950 text-emerald-300 border border-emerald-700'
                    : latestDecision.action === 'MICRO_SLEEP_PACED'
                    ? 'bg-amber-950 text-amber-300 border border-amber-700'
                    : 'bg-rose-950 text-rose-300 border border-rose-700'
                }`}
              >
                {latestDecision.action}
              </span>
            </div>
            <div className="flex items-center justify-between text-slate-400">
              <span>整形施加延迟:</span>
              <span className="font-mono text-cyan-400">{latestDecision.delay_ms} ms</span>
            </div>
            <div className="flex items-center justify-between text-slate-400">
              <span>预测 TPM 水位:</span>
              <span className="font-mono text-slate-200">{latestDecision.tpm_watermark_pct}%</span>
            </div>
            <div className="text-slate-400 pt-1 border-t border-slate-800">
              <span className="text-slate-500">归因解释: </span>
              <span className="text-slate-300">{latestDecision.reason}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
