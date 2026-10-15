'use client';

import React, { useState } from 'react';
import {
  Brain,
  ChevronDown,
  ChevronUp,
  Clock,
  Sparkles,
  CheckCircle2,
  Activity,
  Copy,
  Check,
} from 'lucide-react';
import { useThinkingBudgetStore } from './useThinkingBudgetStore';
import {
  formatElapsedSec,
  formatThinkingTokens,
} from './reasoningTimelineEngine';
import { ReasoningStage } from './thinkingBudgetTypes';

export const InlineReasoningTimelineBox: React.FC = () => {
  const [copied, setCopied] = useState(false);
  const [expandedStageId, setExpandedStageId] = useState<string | null>(null);

  const {
    isThinking,
    isExpanded,
    totalElapsedSec,
    thinkingTokens,
    rawContent,
    stages,
    toggleExpanded,
  } = useThinkingBudgetStore();

  const handleCopy = () => {
    if (!rawContent) {
      return;
    }
    navigator.clipboard.writeText(rawContent).then(() => {
      setCopied(true);
      setTimeout(() => { setCopied(false); }, 2000);
    });
  };

  const toggleStageDetail = (stageId: string) => {
    if (expandedStageId === stageId) {
      setExpandedStageId(null);
    } else {
      setExpandedStageId(stageId);
    }
  };

  if (!rawContent && !isThinking) {
    return null;
  }

  return (
    <div
      className={`my-2 rounded-2xl border transition-all duration-300 select-none ${
        isThinking
          ? 'bg-slate-900/90 border-indigo-500/50 shadow-lg shadow-indigo-950/40 ring-1 ring-indigo-500/30'
          : 'bg-slate-900/60 border-slate-800 hover:border-slate-700/80'
      }`}
    >
      {/* 状态收纳折叠条 */}
      <button
        type="button"
        onClick={() => { toggleExpanded(); }}
        aria-expanded={isExpanded}
        aria-label="展开或收起深度思考思维链"
        className="w-full flex items-center justify-between p-3 rounded-2xl text-left transition-colors hover:bg-slate-800/40"
      >
        <div className="flex items-center space-x-2.5 min-w-0">
          <div
            className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0 ${
              isThinking
                ? 'bg-indigo-500/20 text-indigo-400 animate-pulse'
                : 'bg-slate-800 text-slate-400'
            }`}
          >
            <Brain className="w-3.5 h-3.5" aria-hidden="true" />
          </div>

          <div className="flex items-center space-x-2 truncate text-xs">
            {isThinking ? (
              <span className="font-bold text-indigo-300 flex items-center space-x-1.5">
                <span className="w-2 h-2 rounded-full bg-indigo-400 animate-ping inline-block" />
                <span>深度思考推演中...</span>
              </span>
            ) : (
              <span className="font-semibold text-slate-300">
                已深度思考完成
              </span>
            )}

            <span className="text-slate-600">·</span>

            <span className="text-slate-400 font-mono text-[11px] flex items-center space-x-1">
              <Clock className="w-3 h-3 text-slate-500" aria-hidden="true" />
              <span>{formatElapsedSec(totalElapsedSec)}</span>
            </span>

            {thinkingTokens > 0 && (
              <>
                <span className="text-slate-600">·</span>
                <span className="text-slate-400 font-mono text-[11px] flex items-center space-x-1">
                  <Sparkles className="w-3 h-3 text-amber-500/80" aria-hidden="true" />
                  <span>{formatThinkingTokens(thinkingTokens)} 推理 Tokens</span>
                </span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center space-x-1.5 text-xs text-slate-400 shrink-0 ml-2">
          <span className="hidden sm:inline text-[11px]">
            {isExpanded ? '收起思维链' : '展开详情'}
          </span>
          {isExpanded ? (
            <ChevronUp className="w-4 h-4 text-slate-400" aria-hidden="true" />
          ) : (
            <ChevronDown className="w-4 h-4 text-slate-400" aria-hidden="true" />
          )}
        </div>
      </button>

      {/* 展开后的多阶段结构化时间轴 */}
      {isExpanded && (
        <div className="px-4 pb-4 pt-1 border-t border-slate-800/80 text-xs animate-in fade-in duration-200">
          <div className="flex items-center justify-between py-2 text-[11px] font-semibold text-slate-400">
            <span>推理阶段里程碑 ({stages.length} 个阶段)</span>
            <button
              type="button"
              onClick={handleCopy}
              className="flex items-center space-x-1 px-2 py-0.5 rounded-md hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
              title="复制全部思维链内容"
            >
              {copied ? (
                <>
                  <Check className="w-3 h-3 text-emerald-400" aria-hidden="true" />
                  <span className="text-emerald-400">已复制</span>
                </>
              ) : (
                <>
                  <Copy className="w-3 h-3" aria-hidden="true" />
                  <span>复制思维链</span>
                </>
              )}
            </button>
          </div>

          {/* 纵向时间轴列表 */}
          <div className="relative pl-6 space-y-4 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-800">
            {stages.map((stage: ReasoningStage) => {
              const isStageExpanded = expandedStageId === stage.id;
              const isProgressing = stage.status === 'in-progress';

              return (
                <div key={stage.id} className="relative group">
                  {/* 时间轴节点图标 */}
                  <div className="absolute -left-6 top-0.5">
                    {isProgressing ? (
                      <div className="w-4 h-4 rounded-full bg-indigo-500/20 border border-indigo-400 flex items-center justify-center">
                        <Activity className="w-2.5 h-2.5 text-indigo-400 animate-spin" aria-hidden="true" />
                      </div>
                    ) : (
                      <div className="w-4 h-4 rounded-full bg-emerald-500/20 border border-emerald-500/60 flex items-center justify-center">
                        <CheckCircle2 className="w-3 h-3 text-emerald-400" aria-hidden="true" />
                      </div>
                    )}
                  </div>

                  {/* 阶段标题与耗时 */}
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-slate-200">
                      {stage.title}
                    </span>
                    <span className="text-[10px] font-mono text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded">
                      ~{stage.durationSec}s
                    </span>
                  </div>

                  {/* 阶段摘要卡片 */}
                  <div
                    onClick={() => { toggleStageDetail(stage.id); }}
                    role="presentation"
                    className="p-2.5 rounded-xl bg-slate-800/40 border border-slate-800/80 hover:bg-slate-800/70 cursor-pointer transition-colors"
                  >
                    <p className="text-[11px] text-slate-300 leading-relaxed line-clamp-2">
                      {stage.summary}
                    </p>

                    {isStageExpanded && (
                      <div className="mt-2.5 pt-2 border-t border-slate-700/60 text-[11px] font-mono text-slate-300 whitespace-pre-wrap leading-relaxed bg-slate-950/60 p-2.5 rounded-lg border border-slate-800">
                        {stage.rawContent}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
