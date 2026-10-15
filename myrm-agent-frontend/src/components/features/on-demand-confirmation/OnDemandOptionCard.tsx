import React from 'react';
import { CheckCircle2, Circle, Sparkles } from 'lucide-react';
import { ConfirmationOptionItem } from './onDemandConfirmationTypes';

interface OnDemandOptionCardProps {
  option: ConfirmationOptionItem;
  isSelected: boolean;
  digitShortcut: number;
  onSelect: (id: ConfirmationOptionItem['id']) => void;
}

export const OnDemandOptionCard: React.FC<OnDemandOptionCardProps> = ({
  option,
  isSelected,
  digitShortcut,
  onSelect,
}) => {
  return (
    <button
      type="button"
      onClick={() => onSelect(option.id)}
      data-testid={`on-demand-option-card-${option.id}`}
      className={`w-full text-left p-3.5 rounded-2xl border transition-all relative flex items-start gap-3 cursor-pointer ${
        isSelected
          ? 'bg-indigo-950/60 border-indigo-500 shadow-md ring-1 ring-indigo-500/50'
          : 'bg-slate-900/40 border-slate-800/80 hover:bg-slate-900/80 hover:border-slate-700'
      }`}
    >
      {/* 字母与数字快捷键标记胶囊 */}
      <div
        className={`w-7 h-7 rounded-xl flex items-center justify-center shrink-0 font-bold text-xs font-mono transition-colors border ${
          isSelected
            ? 'bg-indigo-600 border-indigo-400 text-white'
            : 'bg-slate-800/80 border-slate-700 text-slate-300'
        }`}
      >
        <span>{option.id}</span>
      </div>

      {/* 选项文本与描述 */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className={`font-semibold text-sm ${
              isSelected ? 'text-white' : 'text-slate-200'
            }`}
          >
            {option.label}
          </span>

          {option.isRecommended && (
            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/30">
              <Sparkles className="w-2.5 h-2.5" />
              <span>推荐</span>
            </span>
          )}

          {option.tag && (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-400">
              {option.tag}
            </span>
          )}
        </div>

        {option.description && (
          <p className="mt-1 text-xs text-slate-400 leading-relaxed">
            {option.description}
          </p>
        )}
      </div>

      {/* 单选勾选指示与键盘快捷键提示 */}
      <div className="flex flex-col items-end gap-1.5 shrink-0 self-center">
        {isSelected ? (
          <CheckCircle2 className="w-5 h-5 text-indigo-400" />
        ) : (
          <Circle className="w-5 h-5 text-slate-600" />
        )}
        <span className="text-[10px] font-mono text-slate-500">
          [{digitShortcut}]
        </span>
      </div>
    </button>
  );
};
