import React, { useState } from 'react';
import {
  Cpu,
  Clock,
  Sparkles,
  ChevronDown,
  ChevronRight,
  BrainCircuit,
  AlertCircle,
} from 'lucide-react';
import { useArenaStore } from './useArenaStore';
import { AdoptSynthesizeBar } from './AdoptSynthesizeBar';
import type { ArenaModelConfig, ArenaModelStream } from './arenaTypes';

export interface MultiModelSplitArenaViewProps {
  readonly className?: string;
  readonly onSynthesizeRequested?: (synthesizedContent: string) => void;
}

export const MultiModelSplitArenaView: React.FC<MultiModelSplitArenaViewProps> = ({
  className = '',
  onSynthesizeRequested,
}) => {
  const {
    availableModels,
    selectedModelIds,
    streamMap,
    layoutMode,
    adoptedDecision,
  } = useArenaStore();

  const [expandedReasoningMap, setExpandedReasoningMap] = useState<Record<string, boolean>>({});

  const toggleReasoning = (modelId: string) => {
    setExpandedReasoningMap((prev) => {
      return {
        ...prev,
        [modelId]: !prev[modelId],
      };
    });
  };

  const selectedModels = availableModels.filter((m) => {
    return selectedModelIds.includes(m.id);
  });

  const gridColsClass =
    layoutMode === 'split_3'
      ? 'grid-cols-1 md:grid-cols-3'
      : 'grid-cols-1 md:grid-cols-2';

  return (
    <div
      data-testid="multi-model-split-arena"
      className={`flex flex-col gap-3 rounded-2xl border border-slate-700/80 bg-slate-900/90 p-4 shadow-2xl backdrop-blur-md text-slate-100 ${className}`}
    >
      {/* 头部状态条 */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-400">
            <Cpu className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-xs font-semibold text-slate-100">
              多模型分栏对照竞技场
            </h3>
            <p className="text-[10px] text-slate-400">
              单次提问并发扇出至 {selectedModels.length} 个模型 · 实时对比推理与长板
            </p>
          </div>
        </div>

        {adoptedDecision && (
          <div className="flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-[11px] text-emerald-300">
            <Sparkles className="h-3.5 w-3.5" />
            <span>{adoptedDecision.note}</span>
          </div>
        )}
      </div>

      {/* 并排分栏展示区 */}
      <div className={`grid gap-3.5 ${gridColsClass}`}>
        {selectedModels.map((model: ArenaModelConfig) => {
          const stream: ArenaModelStream = streamMap[model.id] ?? {
            modelId: model.id,
            status: 'idle',
            contentText: '',
            latencyMs: 0,
            tokenCount: 0,
          };

          const isReasoningExpanded = Boolean(expandedReasoningMap[model.id]);
          const isAdopted = adoptedDecision?.chosenModelId === model.id;

          return (
            <div
              key={model.id}
              data-testid={`arena-column-${model.id}`}
              className={`flex flex-col justify-between rounded-xl border p-3.5 transition-all duration-200 ${
                isAdopted
                  ? 'border-emerald-500/80 bg-emerald-950/20 ring-1 ring-emerald-500/30'
                  : 'border-slate-800 bg-slate-950/60'
              }`}
            >
              <div>
                {/* 栏目标题与性能元数据 */}
                <div className="flex items-center justify-between gap-2 pb-2.5 border-b border-slate-800/80">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-slate-200 truncate">
                      {model.name}
                    </span>
                    <span className="rounded bg-indigo-500/10 px-1.5 py-0.5 text-[9px] font-medium text-indigo-300">
                      {model.tier}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 text-[10px] text-slate-400">
                    <span className="flex items-center gap-0.5">
                      <Clock className="h-2.5 w-2.5" />
                      {stream.latencyMs}ms
                    </span>
                    <span>{stream.tokenCount} tok</span>
                  </div>
                </div>

                {/* 思考链折叠区域（若模型具备深度推理输出） */}
                {stream.reasoningText && (
                  <div className="my-2 rounded-lg border border-slate-800 bg-slate-900/60 p-2">
                    <button
                      type="button"
                      onClick={() => {
                        toggleReasoning(model.id);
                      }}
                      className="flex w-full items-center justify-between text-[11px] font-medium text-slate-400 hover:text-slate-200"
                    >
                      <span className="flex items-center gap-1">
                        <BrainCircuit className="h-3 w-3 text-indigo-400" />
                        深度思考链 (CoT)
                      </span>
                      {isReasoningExpanded ? (
                        <ChevronDown className="h-3.5 w-3.5" />
                      ) : (
                        <ChevronRight className="h-3.5 w-3.5" />
                      )}
                    </button>
                    {isReasoningExpanded && (
                      <p className="mt-1.5 text-[11px] leading-relaxed text-slate-400 font-mono whitespace-pre-wrap border-t border-slate-800/60 pt-1.5">
                        {stream.reasoningText}
                      </p>
                    )}
                  </div>
                )}

                {/* 核心回复内容展示 */}
                <div className="mt-2 min-h-32 text-xs leading-relaxed text-slate-200">
                  {stream.error ? (
                    <div className="flex items-center gap-1.5 text-rose-400 p-2 rounded bg-rose-500/10 border border-rose-500/20">
                      <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                      <span className="text-[11px]">{stream.error}</span>
                    </div>
                  ) : stream.contentText ? (
                    <div className="whitespace-pre-wrap font-sans text-xs">
                      {stream.contentText}
                    </div>
                  ) : (
                    <div className="flex h-32 items-center justify-center text-[11px] text-slate-500">
                      等待输入并发拉取回复...
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* 底部采纳与智能合成条 */}
      <AdoptSynthesizeBar onSynthesizeRequested={onSynthesizeRequested} />
    </div>
  );
};
