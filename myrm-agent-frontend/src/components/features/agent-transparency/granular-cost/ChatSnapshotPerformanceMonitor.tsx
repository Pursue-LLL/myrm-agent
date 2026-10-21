'use client';

import React from 'react';
import {
  Activity,
  Layers,
  ShieldCheck,
  Zap,
  RotateCw,
  Gauge,
} from 'lucide-react';
import { useAgentGranularCostStore } from './useAgentGranularCostStore';

export const ChatSnapshotPerformanceMonitor: React.FC = () => {
  const {
    throttleConfig,
    throttleMetrics,
    updateThrottleConfig,
    flushStreamingBuffer,
    agentProfiles,
  } = useAgentGranularCostStore();

  const handleThrottleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const ms = Number(e.target.value);
    updateThrottleConfig({ throttleMs: ms });
  };

  const handleFlush = () => {
    if (agentProfiles.length > 0) {
      flushStreamingBuffer(agentProfiles[0].agentId);
    }
  };

  return (
    <div className="flex flex-col p-4 bg-slate-900/80 rounded-2xl border border-slate-800 shadow-xl select-none">
      {/* 头部标题与实时状态 */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-3">
        <div className="flex items-center space-x-2">
          <div className="p-1.5 bg-emerald-500/10 border border-emerald-500/30 rounded-lg">
            <Gauge className="w-4 h-4 text-emerald-400" aria-hidden="true" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-slate-200">
              会话状态快照防卡顿节流引擎
            </h4>
            <p className="text-[11px] text-slate-400">
              消除高频流式增量导致的整树全量快照深拷贝与 GC 掉帧卡顿
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-[10px] text-emerald-300 font-mono">
          <Activity className="w-3 h-3 text-emerald-400 animate-pulse" aria-hidden="true" />
          <span>防抖生效中</span>
        </div>
      </div>

      {/* 指标卡片网格 */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-3.5">
        <div className="p-2.5 rounded-xl bg-slate-800/60 border border-slate-700/60 flex flex-col">
          <span className="text-[10px] text-slate-400 flex items-center space-x-1">
            <Zap className="w-3 h-3 text-amber-400" aria-hidden="true" />
            <span>接收流式增量</span>
          </span>
          <span className="text-sm font-bold font-mono text-slate-100 mt-1">
            {throttleMetrics.totalPatchesReceived}
          </span>
        </div>

        <div className="p-2.5 rounded-xl bg-slate-800/60 border border-slate-700/60 flex flex-col">
          <span className="text-[10px] text-slate-400 flex items-center space-x-1">
            <Layers className="w-3 h-3 text-sky-400" aria-hidden="true" />
            <span>聚合提交快照</span>
          </span>
          <span className="text-sm font-bold font-mono text-sky-300 mt-1">
            {throttleMetrics.snapshotsCommitted}
          </span>
        </div>

        <div className="p-2.5 rounded-xl bg-slate-800/60 border border-slate-700/60 flex flex-col">
          <span className="text-[10px] text-slate-400 flex items-center space-x-1">
            <ShieldCheck className="w-3 h-3 text-emerald-400" aria-hidden="true" />
            <span>消除冗余快照</span>
          </span>
          <span className="text-sm font-bold font-mono text-emerald-400 mt-1">
            {throttleMetrics.redundantSnapshotsPrevented}
          </span>
        </div>

        <div className="p-2.5 rounded-xl bg-slate-800/60 border border-slate-700/60 flex flex-col">
          <span className="text-[10px] text-slate-400 flex items-center space-x-1">
            <Activity className="w-3 h-3 text-indigo-400" aria-hidden="true" />
            <span>GC 压力削减率</span>
          </span>
          <span className="text-sm font-bold font-mono text-indigo-300 mt-1">
            {throttleMetrics.reductionRatePercentage}%
          </span>
        </div>
      </div>

      {/* 底部调节控制条 */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2.5 border-t border-slate-800 text-xs">
        <div className="flex items-center space-x-2">
          <label htmlFor="throttle-range-slider" className="text-slate-400 text-[11px]">
            动态节流窗口:
          </label>
          <input
            id="throttle-range-slider"
            type="range"
            min="100"
            max="1000"
            step="50"
            value={throttleConfig.throttleMs}
            onChange={handleThrottleChange}
            className="w-28 h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-emerald-500"
          />
          <span className="font-mono text-slate-200 text-[11px] w-12">
            {throttleConfig.throttleMs}ms
          </span>
        </div>

        <button
          type="button"
          onClick={handleFlush}
          className="flex items-center space-x-1 px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition-colors"
          title="强制立即提交当前未冲刷的流式增量"
        >
          <RotateCw className="w-3 h-3 text-slate-400" aria-hidden="true" />
          <span>立即冲刷</span>
        </button>
      </div>
    </div>
  );
};
