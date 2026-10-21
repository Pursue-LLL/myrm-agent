'use client';

import React, { useRef, useEffect } from 'react';
import {
  Brain,
  ChevronDown,
  Check,
  Zap,
  Sliders,
  Sparkles,
} from 'lucide-react';
import { useThinkingBudgetStore } from './useThinkingBudgetStore';
import { BUDGET_OPTIONS } from './reasoningTimelineEngine';
import { ThinkingBudgetLevel } from './thinkingBudgetTypes';

export const InlineThinkingBudgetSelector: React.FC = () => {
  const popoverRef = useRef<HTMLDivElement>(null);
  const {
    currentBudgetLevel,
    isThinkingCapable,
    isSelectorOpen,
    setBudgetLevel,
    toggleSelector,
  } = useThinkingBudgetStore();

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        toggleSelector(false);
      }
    };
    if (isSelectorOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isSelectorOpen, toggleSelector]);

  if (!isThinkingCapable) {
    return null;
  }

  const currentOption = BUDGET_OPTIONS[currentBudgetLevel];

  const getLevelBadgeColor = (level: ThinkingBudgetLevel) => {
    switch (level) {
      case 'off':
        return 'text-slate-400 bg-slate-800/80 border-slate-700/80';
      case 'low':
        return 'text-sky-300 bg-sky-500/15 border-sky-500/30';
      case 'medium':
        return 'text-indigo-300 bg-indigo-500/15 border-indigo-500/30';
      case 'high':
        return 'text-amber-300 bg-amber-500/15 border-amber-500/30';
      default:
        return 'text-slate-300 bg-slate-800 border-slate-700';
    }
  };

  const getLevelIcon = (level: ThinkingBudgetLevel) => {
    switch (level) {
      case 'off':
        return <Sliders className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />;
      case 'low':
        return <Zap className="w-3.5 h-3.5 text-sky-400" aria-hidden="true" />;
      case 'medium':
        return <Brain className="w-3.5 h-3.5 text-indigo-400" aria-hidden="true" />;
      case 'high':
        return <Sparkles className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" />;
      default:
        return <Brain className="w-3.5 h-3.5" aria-hidden="true" />;
    }
  };

  return (
    <div className="relative inline-block select-none">
      <button
        type="button"
        onClick={() => { toggleSelector(); }}
        aria-label="选择模型深度思考预算"
        className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-all duration-150 ${getLevelBadgeColor(
          currentBudgetLevel
        )} hover:opacity-90 active:scale-[0.98]`}
        title={`当前思考预算: ${currentOption.label} · ${currentOption.description}`}
      >
        {getLevelIcon(currentBudgetLevel)}
        <span className="font-semibold">{currentOption.label}</span>
        <ChevronDown
          className={`w-3 h-3 text-slate-400 transition-transform ${
            isSelectorOpen ? 'rotate-180 text-sky-400' : ''
          }`}
          aria-hidden="true"
        />
      </button>

      {/* 弹出的极简微调档位气泡浮层 */}
      {isSelectorOpen && (
        <div
          ref={popoverRef}
          className="absolute bottom-full left-0 mb-2 z-50 w-64 p-2 bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl backdrop-blur-xl animate-in fade-in zoom-in-95 duration-150"
        >
          <div className="flex items-center justify-between pb-1.5 mb-1.5 border-b border-slate-800 px-1 text-[11px] font-semibold text-slate-400">
            <span>自适应推理预算设定</span>
            <span className="text-[10px] text-slate-500 font-mono">Thinking Budget</span>
          </div>

          <div className="space-y-1">
            {(
              ['off', 'low', 'medium', 'high'] as ThinkingBudgetLevel[]
            ).map((level) => {
              const opt = BUDGET_OPTIONS[level];
              const isSelected = currentBudgetLevel === level;

              return (
                <button
                  key={level}
                  type="button"
                  onClick={() => { setBudgetLevel(level); }}
                  className={`w-full text-left p-2 rounded-xl text-xs transition-colors flex items-start justify-between ${
                    isSelected
                      ? 'bg-slate-800 border border-indigo-500/40'
                      : 'hover:bg-slate-800/60 border border-transparent'
                  }`}
                >
                  <div className="min-w-0 pr-2">
                    <div className="flex items-center space-x-1.5">
                      {getLevelIcon(level)}
                      <span className="font-bold text-slate-200 truncate">
                        {opt.label}
                      </span>
                      <span className="text-[10px] text-slate-400 font-mono">
                        ~{opt.estSeconds}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">
                      {opt.description}
                    </p>
                  </div>

                  {isSelected && (
                    <div className="mt-1 w-4 h-4 rounded-full bg-indigo-600 text-white flex items-center justify-center shrink-0">
                      <Check className="w-2.5 h-2.5 stroke-[3]" aria-hidden="true" />
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
