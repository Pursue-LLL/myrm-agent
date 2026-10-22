/**
 * [INPUT]: SessionSavingsAudit data, modal open state, and export handlers.
 * [OUTPUT]: Modal window visualizing per-tool token truncation savings, financial ROI (CNY/USD), and cash-in-hand war reports.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/ContextSavingsWarReportModal.tsx
 */

import React from 'react';
import type { SessionSavingsAudit } from './contextSavingsTypes';

export interface ContextSavingsWarReportModalProps {
  isOpen: boolean;
  audit: SessionSavingsAudit | null;
  onClose: () => void;
  onExportJson?: () => void;
}

export const ContextSavingsWarReportModal: React.FC<ContextSavingsWarReportModalProps> = ({
  isOpen,
  audit,
  onClose,
  onExportJson,
}) => {
  if (!isOpen || !audit) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="上下文拦截节流战报"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
    >
      <div className="w-full max-w-3xl bg-slate-900 border border-slate-700/80 rounded-xl shadow-2xl flex flex-col max-h-[90vh] overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-850/60">
          <div className="flex items-center gap-2.5">
            <span className="text-2xl">🪙</span>
            <div>
              <h2 className="text-base font-semibold text-white">上下文拦截节流战报</h2>
              <p className="text-xs text-slate-400 mt-0.5 font-mono">
                会话: {audit.session_id} · 智能体沙箱外部化与缓存提效
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1.5 rounded-lg hover:bg-slate-800 transition-colors"
            aria-label="关闭战报"
          >
            ✕
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto space-y-5">
          {/* Headline Banner */}
          <div className="p-3.5 rounded-lg bg-gradient-to-r from-emerald-950/60 via-slate-850/60 to-cyan-950/60 border border-emerald-800/60 text-xs text-emerald-300 flex items-center gap-2">
            <span className="text-base">🎉</span>
            <span className="font-medium leading-relaxed">{audit.summary_headline}</span>
          </div>

          {/* KPI Triad */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="p-4 rounded-lg bg-slate-800/60 border border-slate-750">
              <div className="text-[11px] font-medium text-slate-400">智能拦截节省 Token</div>
              <div className="mt-1 flex items-baseline gap-1.5">
                <span className="text-2xl font-bold font-mono text-emerald-400">
                  {audit.total_saved_tokens.toLocaleString()}
                </span>
                <span className="text-xs text-slate-500">Tokens</span>
              </div>
            </div>

            <div className="p-4 rounded-lg bg-slate-800/60 border border-slate-750">
              <div className="text-[11px] font-medium text-slate-400">整体上下文节省率</div>
              <div className="mt-1 flex items-baseline gap-1.5">
                <span className="text-2xl font-bold font-mono text-cyan-400">
                  {audit.overall_savings_rate_pct}%
                </span>
                <span className="text-xs text-slate-500">截断提效</span>
              </div>
            </div>

            <div className="p-4 rounded-lg bg-slate-800/60 border border-slate-750">
              <div className="text-[11px] font-medium text-slate-400">折合挽回财务开销</div>
              <div className="mt-1 flex items-baseline gap-1.5">
                <span className="text-2xl font-bold font-mono text-amber-400">
                  ¥{audit.total_cost_saved_cny.toFixed(2)}
                </span>
                <span className="text-xs text-slate-500">(${audit.total_cost_saved_usd.toFixed(2)})</span>
              </div>
            </div>
          </div>

          {/* Breakdown Table */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                每工具节流效益量化明细 ({audit.tool_breakdown.length})
              </h3>
              <span className="text-[11px] text-slate-500">按节省 Token 降序排列</span>
            </div>

            {audit.tool_breakdown.length === 0 ? (
              <div className="p-8 text-center text-slate-500 bg-slate-850/40 rounded-lg border border-dashed border-slate-800">
                本次会话暂无工具调用截断记录
              </div>
            ) : (
              <div className="border border-slate-800 rounded-lg overflow-hidden">
                <table className="w-full text-left border-collapse text-xs">
                  <thead className="bg-slate-850 text-slate-400 border-b border-slate-800">
                    <tr>
                      <th className="py-2.5 px-3 font-medium">工具名称</th>
                      <th className="py-2.5 px-3 font-medium">调用次数</th>
                      <th className="py-2.5 px-3 font-medium">原始 Tokens</th>
                      <th className="py-2.5 px-3 font-medium">优化后 Tokens</th>
                      <th className="py-2.5 px-3 font-medium">节省率</th>
                      <th className="py-2.5 px-3 font-medium">缓存命中</th>
                      <th className="py-2.5 px-3 font-medium text-right">挽回金额 (¥)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/80 bg-slate-900/60 text-slate-300">
                    {audit.tool_breakdown.map((row) => (
                      <tr key={row.tool_name} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-2.5 px-3 font-mono font-medium text-cyan-300">
                          {row.tool_name}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-slate-400">
                          {row.total_calls}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-slate-400">
                          {row.total_original_tokens.toLocaleString()}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-slate-400">
                          {row.total_optimized_tokens.toLocaleString()}
                        </td>
                        <td className="py-2.5 px-3 font-mono">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                              row.average_savings_rate_pct >= 90
                                ? 'bg-emerald-950 text-emerald-300 border border-emerald-800/60'
                                : 'bg-cyan-950 text-cyan-300 border border-cyan-800/60'
                            }`}
                          >
                            {row.average_savings_rate_pct}%
                          </span>
                        </td>
                        <td className="py-2.5 px-3 font-mono text-slate-400">
                          {row.cache_hit_rate_pct}%
                        </td>
                        <td className="py-2.5 px-3 font-mono text-right font-medium text-amber-300">
                          ¥{row.total_cost_saved_cny.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-3.5 border-t border-slate-800 bg-slate-850/40">
          <button
            type="button"
            onClick={onExportJson}
            className="px-3.5 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-750 text-slate-200 border border-slate-700 transition-colors flex items-center gap-1.5"
          >
            <span>📥</span>
            <span>导出 .savings.json</span>
          </button>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-xs font-medium rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white transition-colors"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
};
