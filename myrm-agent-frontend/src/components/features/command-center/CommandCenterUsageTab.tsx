import React from 'react';
import {
  BarChart3,
  Cpu,
  Wrench,
  Layers,
  DollarSign,
  CheckCircle2,
} from 'lucide-react';
import { useCommandCenterStore } from './useCommandCenterStore';
import { UsageHorizon } from './commandCenterTypes';

export const CommandCenterUsageTab: React.FC = () => {
  const { usageHorizon, usageSummary, setUsageHorizon } = useCommandCenterStore();

  const horizonButtons: UsageHorizon[] = [7, 30, 90];

  const formatTokens = (tokens: number): string => {
    if (tokens >= 1000000) {
      return `${(tokens / 1000000).toFixed(1)}M`;
    }
    if (tokens >= 1000) {
      return `${(tokens / 1000).toFixed(1)}k`;
    }
    return `${tokens}`;
  };

  return (
    <div
      data-testid="command-center-usage-tab"
      className="flex flex-col h-[460px] select-none text-slate-200 overflow-y-auto pr-1"
    >
      {/* 顶部跨度切换 */}
      <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-indigo-400" />
          <span className="font-semibold text-xs text-slate-100">
            用量与资产透视大盘
          </span>
        </div>
        <div className="flex items-center bg-slate-900 p-0.5 rounded-lg border border-slate-800 text-xs">
          {horizonButtons.map((horizon) => (
            <button
              key={horizon}
              type="button"
              onClick={() => setUsageHorizon(horizon)}
              className={`px-3 py-1 rounded-md text-[11px] font-medium transition-colors ${
                usageHorizon === horizon
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {horizon} 天用量
            </button>
          ))}
        </div>
      </div>

      {/* 核心指标 4 卡 */}
      <div className="grid grid-cols-4 gap-2.5 mb-4">
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-3">
          <div className="text-[11px] text-slate-400 flex items-center justify-between">
            <span>SESSIONS</span>
            <Layers className="w-3.5 h-3.5 text-indigo-400" />
          </div>
          <div className="mt-1.5 text-base font-bold text-slate-100 font-mono">
            {usageSummary.totalSessions.toLocaleString()}
          </div>
          <span className="text-[10px] text-slate-500">累计执行会话</span>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-3">
          <div className="text-[11px] text-slate-400 flex items-center justify-between">
            <span>API CALLS</span>
            <Cpu className="w-3.5 h-3.5 text-sky-400" />
          </div>
          <div className="mt-1.5 text-base font-bold text-slate-100 font-mono">
            {usageSummary.totalApiCalls.toLocaleString()}
          </div>
          <span className="text-[10px] text-slate-500">网关请求总数</span>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-3">
          <div className="text-[11px] text-slate-400 flex items-center justify-between">
            <span>TOKENS IN</span>
            <span className="w-2 h-2 rounded-full bg-blue-500" />
          </div>
          <div className="mt-1.5 text-base font-bold text-blue-400 font-mono">
            {formatTokens(usageSummary.tokensIn)}
          </div>
          <span className="text-[10px] text-slate-500">上下文输入 Token</span>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-3">
          <div className="text-[11px] text-slate-400 flex items-center justify-between">
            <span>TOKENS OUT</span>
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
          </div>
          <div className="mt-1.5 text-base font-bold text-emerald-400 font-mono">
            {formatTokens(usageSummary.tokensOut)}
          </div>
          <span className="text-[10px] text-slate-500">模型生成 Token</span>
        </div>
      </div>

      {/* 双杀手级排行榜并排 */}
      <div className="grid grid-cols-2 gap-3 flex-1">
        {/* Top Models 排行 */}
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-3 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800 text-xs">
              <span className="font-semibold text-slate-200">Top Models 消耗占比</span>
              <span className="text-[10px] text-slate-500">Token 占比</span>
            </div>
            <div className="space-y-2.5">
              {usageSummary.topModels.map((m) => (
                <div key={m.modelId} className="space-y-1">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="font-medium text-slate-300">{m.modelName}</span>
                    <span className="font-mono text-slate-400">
                      {formatTokens(m.tokenCount)} ({m.percentage}%)
                    </span>
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                    <div
                      className="bg-indigo-500 h-1.5 rounded-full"
                      style={{ width: `${m.percentage}%` }}
                    />
                  </div>
                  <div className="flex items-center justify-end text-[10px] text-slate-500">
                    <DollarSign className="w-2.5 h-2.5" />
                    <span>预估花费: ${m.costEstimateUsd.toFixed(2)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Top Skills Actions 排行 */}
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-3 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800 text-xs">
              <span className="font-semibold text-slate-200">
                Top Skills Actions 动作排行
              </span>
              <Wrench className="w-3.5 h-3.5 text-amber-400" />
            </div>
            <div className="space-y-2.5">
              {usageSummary.topSkills.map((s) => (
                <div
                  key={s.skillId}
                  className="p-2 rounded-lg bg-slate-950/60 border border-slate-800/80 flex items-center justify-between"
                >
                  <div className="min-w-0 pr-2">
                    <div className="text-[11px] font-semibold text-slate-200 truncate">
                      {s.skillName}
                    </div>
                    <div className="mt-0.5 flex items-center gap-1 text-[10px] text-emerald-400">
                      <CheckCircle2 className="w-3 h-3" />
                      <span>成功率 {s.successRate}%</span>
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <span className="text-xs font-bold font-mono text-amber-400">
                      {s.actionCount}
                    </span>
                    <span className="text-[10px] text-slate-500 ml-1">actions</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
