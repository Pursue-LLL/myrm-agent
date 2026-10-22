import React from 'react';
import { Brain, Zap, Scale, Compass, CheckCircle2 } from 'lucide-react';
import { COGNITIVE_TIERS } from './useBotCreatorStudioStore';
import type { CognitiveTier } from './botCreatorStudioTypes';

interface CognitiveTieringSelectorProps {
  selectedTier: CognitiveTier;
  onSelectTier: (tier: CognitiveTier) => void;
  disabledCustomModel?: boolean;
}

export const CognitiveTieringSelector: React.FC<CognitiveTieringSelectorProps> = ({
  selectedTier,
  onSelectTier,
}) => {
  return (
    <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-900/60 p-3.5 backdrop-blur-sm">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center space-x-1.5">
          <Brain className="h-4 w-4 text-purple-400" />
          <span className="text-xs font-semibold text-slate-100">
            多层次大脑认知分级推荐
          </span>
          <span className="rounded bg-purple-500/10 px-1.5 py-0.2 text-[10px] font-medium text-purple-300">
            算力场景精准配型
          </span>
        </div>
        <span className="text-[11px] text-slate-400">拒绝盲目绑定高昂算力</span>
      </div>

      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
        {(Object.keys(COGNITIVE_TIERS) as CognitiveTier[]).map((tierKey) => {
          const tier = COGNITIVE_TIERS[tierKey];
          const isSelected = selectedTier === tierKey;

          return (
            <button
              key={tierKey}
              type="button"
              aria-label={`选择${tier.name}`}
              onClick={() => {
                onSelectTier(tierKey);
              }}
              className={`flex flex-col justify-between rounded-lg border p-3 text-left transition-all ${
                isSelected
                  ? 'border-purple-500/70 bg-purple-950/25 shadow-sm'
                  : 'border-slate-800 bg-slate-850/60 hover:border-slate-700 hover:bg-slate-800/40'
              }`}
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-200">{tier.name}</span>
                  {isSelected ? (
                    <CheckCircle2 className="h-4 w-4 text-purple-400" />
                  ) : tierKey === 'fast_flash' ? (
                    <Zap className="h-3.5 w-3.5 text-amber-400" />
                  ) : tierKey === 'balanced_standard' ? (
                    <Scale className="h-3.5 w-3.5 text-blue-400" />
                  ) : (
                    <Compass className="h-3.5 w-3.5 text-purple-400" />
                  )}
                </div>

                <span className="mt-1 inline-block rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300">
                  {tier.badge}
                </span>

                <p className="mt-2 text-[11px] text-slate-400 leading-snug">
                  {tier.description}
                </p>
              </div>

              <div className="mt-3 border-t border-slate-800/80 pt-2">
                <div className="text-[10px] text-slate-400">推荐代表模型:</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {tier.sampleModels.map((m) => (
                    <span
                      key={m}
                      className="rounded bg-slate-900 px-1.5 py-0.5 font-mono text-[9px] text-slate-300 border border-slate-800"
                    >
                      {m}
                    </span>
                  ))}
                </div>
                <div className="mt-1.5 text-[10px] text-emerald-400">
                  {tier.costEfficiencyRatio}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
