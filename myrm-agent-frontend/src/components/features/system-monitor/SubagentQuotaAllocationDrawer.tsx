/**
 * [INPUT]: SubagentQuotaSlice records, active workspace ID, and reset callbacks.
 * [OUTPUT]: Slide-over drawer rendering isolated subagent TPM allocations and anti-starvation throttling badges.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/SubagentQuotaAllocationDrawer.tsx
 */

import React from 'react';
import type { SubagentQuotaSlice } from './rateLimitGovernorTypes';

export interface SubagentQuotaAllocationDrawerProps {
  isOpen: boolean;
  workspaceId: string;
  slices: SubagentQuotaSlice[];
  onClose: () => void;
  onResetWindow?: (workspaceId: string) => void;
}

export const SubagentQuotaAllocationDrawer: React.FC<SubagentQuotaAllocationDrawerProps> = ({
  isOpen,
  workspaceId,
  slices,
  onClose,
  onResetWindow,
}) => {
  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="子 Agent 隔离配额切片管理"
      className="fixed inset-0 z-50 overflow-hidden bg-black/60 backdrop-blur-sm flex justify-end"
    >
      <div className="w-full max-w-xl bg-slate-900 border-l border-slate-700/80 p-6 flex flex-col justify-between shadow-2xl h-full animate-in slide-in-from-right duration-200">
        <div className="flex-1 overflow-y-auto space-y-5">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-800 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xl">🛡️</span>
                <h2 className="text-lg font-semibold text-white">子 Agent 隔离配额切片管理</h2>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                工作区: <code className="text-cyan-400 font-mono">{workspaceId}</code> · 动态削峰防饿死
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
              aria-label="关闭抽屉"
            >
              ✕
            </button>
          </div>

          {/* Core Principle Banner */}
          <div className="bg-cyan-950/40 border border-cyan-800/60 rounded-lg p-3 text-xs text-cyan-200 space-y-1">
            <div className="font-semibold flex items-center gap-1.5">
              <span>💡</span>
              <span>反贪婪独立切片隔离原则</span>
            </div>
            <p className="text-cyan-300/80 leading-relaxed">
              每个并发子 Agent 拥有独立 TPM 滑动窗口。单任务爆发式高消耗将就地触发切片限流，严防拖垮同工作区其他子任务。
            </p>
          </div>

          {/* Slices List */}
          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              当前并发切片 ({slices.length})
            </h3>
            {slices.length === 0 ? (
              <div className="p-8 text-center text-slate-500 bg-slate-850/50 rounded-lg border border-dashed border-slate-800">
                暂无分配的子 Agent 切片记录
              </div>
            ) : (
              <div className="space-y-2.5">
                {slices.map((slice) => {
                  const usagePct = Math.min(
                    100,
                    Math.round((slice.consumed_tokens_in_window / Math.max(1, slice.allocated_tpm_share)) * 100),
                  );
                  return (
                    <div
                      key={slice.subagent_id}
                      className={`p-3.5 rounded-lg border transition-all ${
                        slice.is_throttled
                          ? 'bg-rose-950/30 border-rose-700/60'
                          : 'bg-slate-800/60 border-slate-700/50 hover:border-slate-600'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-sm font-medium text-slate-200">
                            {slice.subagent_id}
                          </span>
                          {slice.is_throttled ? (
                            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-900/60 text-rose-300 border border-rose-700">
                              ⛔ 切片熔断限流
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-900/60 text-emerald-300 border border-emerald-700">
                              ✓ 正常流通
                            </span>
                          )}
                        </div>
                        <span className="text-xs text-slate-400 font-mono">
                          水位 {usagePct}%
                        </span>
                      </div>

                      {/* Progress Bar */}
                      <div className="w-full bg-slate-900/80 rounded-full h-1.5 overflow-hidden mb-2">
                        <div
                          className={`h-full transition-all duration-300 ${
                            slice.is_throttled
                              ? 'bg-rose-500'
                              : usagePct > 80
                              ? 'bg-amber-400'
                              : 'bg-emerald-400'
                          }`}
                          style={{ width: `${usagePct}%` }}
                        />
                      </div>

                      <div className="grid grid-cols-3 gap-2 text-xs text-slate-400">
                        <div>
                          <div className="text-[10px] text-slate-500">分配限额</div>
                          <div className="font-mono text-slate-300">{slice.allocated_tpm_share.toLocaleString()} TPM</div>
                        </div>
                        <div>
                          <div className="text-[10px] text-slate-500">窗口已耗</div>
                          <div className="font-mono text-slate-300">{slice.consumed_tokens_in_window.toLocaleString()}</div>
                        </div>
                        <div>
                          <div className="text-[10px] text-slate-500">剩余可用</div>
                          <div className={`font-mono ${slice.remaining_tokens_in_window === 0 ? 'text-rose-400' : 'text-slate-300'}`}>
                            {slice.remaining_tokens_in_window.toLocaleString()}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Footer Actions */}
        <div className="pt-4 border-t border-slate-800 flex items-center justify-between">
          <button
            type="button"
            onClick={() => onResetWindow?.(workspaceId)}
            className="px-3.5 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors"
          >
            🔄 一键重置窗口切片
          </button>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-xs font-medium rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white transition-colors"
          >
            完成
          </button>
        </div>
      </div>
    </div>
  );
};
