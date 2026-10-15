'use client';

import React, { useRef } from 'react';
import {
  BrainCircuit,
  Code2,
  ShieldAlert,
  Coins,
  Cpu,
  Zap,
  TrendingUp,
} from 'lucide-react';
import { AgentTokenCostProfile } from './granularCostTypes';
import { formatCostUsd, formatTokenCount } from './chatSnapshotThrottleEngine';
import { useAgentGranularCostStore } from './useAgentGranularCostStore';

interface AgentGranularCostRowProps {
  profile: AgentTokenCostProfile;
}

export const AgentGranularCostRow: React.FC<AgentGranularCostRowProps> = ({ profile }) => {
  const popoverRef = useRef<HTMLDivElement>(null);
  const { activeHoveredAgentId, setActiveHoveredAgentId } = useAgentGranularCostStore();

  const isHovered = activeHoveredAgentId === profile.agentId;

  const renderAvatarIcon = () => {
    switch (profile.avatarIconName) {
      case 'BrainCircuit':
        return <BrainCircuit className="w-4 h-4 text-sky-400" aria-hidden="true" />;
      case 'Code2':
        return <Code2 className="w-4 h-4 text-emerald-400" aria-hidden="true" />;
      case 'ShieldAlert':
        return <ShieldAlert className="w-4 h-4 text-amber-400" aria-hidden="true" />;
      default:
        return <Cpu className="w-4 h-4 text-indigo-400" aria-hidden="true" />;
    }
  };

  const promptPercent =
    profile.totalTokens > 0
      ? Math.round((profile.promptTokens / profile.totalTokens) * 100)
      : 50;

  return (
    <div
      role="presentation"
      onMouseEnter={() => { setActiveHoveredAgentId(profile.agentId); }}
      onMouseLeave={() => { setActiveHoveredAgentId(null); }}
      className="relative flex items-center justify-between p-3 rounded-xl bg-slate-900/60 border border-slate-800/80 hover:bg-slate-800/60 hover:border-slate-700 transition-all duration-200 select-none"
    >
      {/* 左侧：Agent 身份与职责 */}
      <div className="flex items-center space-x-3 min-w-0 pr-4">
        <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center shrink-0">
          {renderAvatarIcon()}
        </div>

        <div className="min-w-0">
          <div className="flex items-center space-x-1.5 truncate">
            <span className="text-xs font-bold text-slate-200 truncate">
              {profile.agentName}
            </span>
          </div>
          <p className="text-[11px] text-slate-400 truncate mt-0.5">
            {profile.role}
          </p>
        </div>
      </div>

      {/* 右侧：微型半透明 Token & 费用指示徽章 */}
      <div className="flex items-center space-x-2 shrink-0">
        <div className="flex flex-col items-end">
          <div className="flex items-center space-x-1.5 px-2 py-0.5 rounded-md bg-slate-800/90 border border-slate-700/80 text-[11px] font-mono">
            <Coins className="w-3 h-3 text-amber-400 shrink-0" aria-hidden="true" />
            <span className="text-slate-300 font-medium">
              {formatTokenCount(profile.totalTokens)}
            </span>
            <span className="text-slate-500">·</span>
            <span className="text-emerald-400 font-semibold">
              {formatCostUsd(profile.estimatedCostUsd)}
            </span>
          </div>

          {/* 细分比例条 (Prompt vs Completion) */}
          <div className="w-24 h-1.5 bg-slate-800 rounded-full overflow-hidden mt-1 flex">
            <div
              style={{ width: `${promptPercent}%` }}
              className="h-full bg-sky-500/80"
              title={`提示词: ${promptPercent}%`}
            />
            <div
              style={{ width: `${100 - promptPercent}%` }}
              className="h-full bg-emerald-500/80"
              title={`生成量: ${100 - promptPercent}%`}
            />
          </div>
        </div>
      </div>

      {/* 悬停浮层：细粒度计费剖析与迷你历史走势 */}
      {isHovered && (
        <div
          ref={popoverRef}
          className="absolute right-0 top-full mt-2 z-40 w-72 p-3 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl backdrop-blur-xl animate-in fade-in zoom-in-95 duration-150"
        >
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800">
            <div className="flex items-center space-x-1.5">
              <Zap className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" />
              <span className="text-xs font-bold text-slate-200">
                算力消耗与成本透视
              </span>
            </div>
            <span className="text-[10px] text-slate-400 font-mono">
              {profile.agentId}
            </span>
          </div>

          {/* 细分子项 */}
          <div className="space-y-1.5 text-xs">
            <div className="flex items-center justify-between text-slate-300">
              <span className="flex items-center">
                <span className="w-2 h-2 rounded-full bg-sky-500 mr-1.5" />
                输入提示词 (Prompt):
              </span>
              <span className="font-mono text-slate-200">
                {profile.promptTokens.toLocaleString()}
              </span>
            </div>

            <div className="flex items-center justify-between text-slate-300">
              <span className="flex items-center">
                <span className="w-2 h-2 rounded-full bg-emerald-500 mr-1.5" />
                模型生成量 (Completion):
              </span>
              <span className="font-mono text-slate-200">
                {profile.completionTokens.toLocaleString()}
              </span>
            </div>

            <div className="flex items-center justify-between text-slate-300">
              <span className="flex items-center">
                <span className="w-2 h-2 rounded-full bg-indigo-500 mr-1.5" />
                上下文缓存命中 (Cached):
              </span>
              <span className="font-mono text-indigo-300">
                {profile.cachedTokens.toLocaleString()}
              </span>
            </div>

            <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between font-semibold">
              <span className="text-slate-300">折算美金总计:</span>
              <span className="font-mono text-emerald-400">
                {formatCostUsd(profile.estimatedCostUsd)}
              </span>
            </div>
          </div>

          {/* 迷你历史柱状走势图 */}
          <div className="mt-3 pt-2.5 border-t border-slate-800">
            <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1.5">
              <span className="flex items-center space-x-1">
                <TrendingUp className="w-3 h-3 text-sky-400" aria-hidden="true" />
                <span>近几次调度负载</span>
              </span>
              <span>Tokens / 次</span>
            </div>

            <div className="flex items-end space-x-1.5 h-10 pt-1">
              {profile.historyPoints.map((point, idx) => {
                const maxTokens = Math.max(
                  ...profile.historyPoints.map((p) => p.tokens),
                  1
                );
                const barHeight = Math.max(
                  8,
                  Math.round((point.tokens / maxTokens) * 36)
                );

                return (
                  <div
                    key={`${point.timestamp}-${idx}`}
                    className="flex-1 flex flex-col items-center group/bar"
                  >
                    <div
                      style={{ height: `${barHeight}px` }}
                      className="w-full bg-sky-500/70 hover:bg-sky-400 rounded-sm transition-all"
                      title={`批次 ${idx + 1}: ${point.tokens} tokens · ${formatCostUsd(point.cost)}`}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
