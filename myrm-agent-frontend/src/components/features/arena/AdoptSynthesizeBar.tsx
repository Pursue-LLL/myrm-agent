import React from 'react';
import { CheckCircle2, Sparkles, Combine } from 'lucide-react';
import { useArenaStore } from './useArenaStore';
import { buildSynthesizePrompt } from './arenaEngine';

export interface AdoptSynthesizeBarProps {
  readonly className?: string;
  readonly onSynthesizeRequested?: (synthesizedContent: string) => void;
}

export const AdoptSynthesizeBar: React.FC<AdoptSynthesizeBarProps> = ({
  className = '',
  onSynthesizeRequested,
}) => {
  const {
    availableModels,
    selectedModelIds,
    streamMap,
    promptQuery,
    adoptSingleSolution,
    synthesizeSolutions,
  } = useArenaStore();

  const selectedModels = availableModels.filter((m) => {
    return selectedModelIds.includes(m.id);
  });

  const streams = selectedModelIds.map((id) => {
    return (
      streamMap[id] ?? {
        modelId: id,
        status: 'idle',
        contentText: '',
        latencyMs: 0,
        tokenCount: 0,
      }
    );
  });

  const hasAnyContent = streams.some((s) => {
    return s.contentText.trim().length > 0;
  });

  const handleSynthesize = () => {
    const prompt = buildSynthesizePrompt(promptQuery, streams);
    synthesizeSolutions(prompt);
    if (onSynthesizeRequested) {
      onSynthesizeRequested(prompt);
    }
  };

  return (
    <div
      data-testid="adopt-synthesize-bar"
      className={`mt-2 flex flex-wrap items-center justify-between gap-2.5 rounded-xl border border-slate-800 bg-slate-950/70 p-3 ${className}`}
    >
      <div className="flex items-center gap-2 text-xs text-slate-400">
        <Combine className="h-4 w-4 text-indigo-400" />
        <span className="font-medium text-slate-300">多模决策决胜</span>
        <span className="hidden sm:inline text-[11px] text-slate-500">
          一键采纳单方结果，或提炼综合两方长板
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {selectedModels.map((model) => {
          return (
            <button
              key={model.id}
              type="button"
              disabled={!hasAnyContent}
              onClick={() => {
                adoptSingleSolution(model.id);
              }}
              className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-200 transition-colors hover:border-slate-600 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
              <span>采纳 {model.name.split(' ')[0]}</span>
            </button>
          );
        })}

        <button
          type="button"
          disabled={!hasAnyContent}
          onClick={handleSynthesize}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-medium text-white shadow-xs transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Sparkles className="h-3.5 w-3.5" />
          <span>融合双模长板</span>
        </button>
      </div>
    </div>
  );
};
