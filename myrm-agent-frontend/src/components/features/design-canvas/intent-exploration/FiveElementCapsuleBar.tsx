'use client';

import React, { useRef, useEffect } from 'react';
import {
  CheckCircle2,
  PlusCircle,
  Wand2,
  Sparkles,
  ChevronDown,
  X,
  Compass,
} from 'lucide-react';
import { useDesignIntentStore } from './useDesignIntentStore';
import { DesignElementKey, DesignElementItem } from './designIntentTypes';

export const FiveElementCapsuleBar: React.FC = () => {
  const popoverRef = useRef<HTMLDivElement>(null);
  const {
    currentSpec,
    activeCapsuleKey,
    setActiveCapsuleKey,
    setElementValue,
    clearElementValue,
    applyAssembledPrompt,
    generateVariants,
  } = useDesignIntentStore();

  const keys: DesignElementKey[] = ['what', 'audience', 'style', 'content', 'format'];

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setActiveCapsuleKey(null);
      }
    };
    if (activeCapsuleKey) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [activeCapsuleKey, setActiveCapsuleKey]);

  const handleCapsuleClick = (key: DesignElementKey) => {
    if (activeCapsuleKey === key) {
      setActiveCapsuleKey(null);
    } else {
      setActiveCapsuleKey(key);
    }
  };

  const renderCapsule = (item: DesignElementItem) => {
    const isActive = activeCapsuleKey === item.key;
    const isFilled = item.isDetected && Boolean(item.value);

    return (
      <div key={item.key} className="relative inline-block">
        <button
          type="button"
          onClick={() => { handleCapsuleClick(item.key); }}
          className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all ${
            isFilled
              ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40 hover:bg-sky-500/30'
              : 'bg-slate-800/80 text-slate-400 border border-dashed border-slate-700 hover:border-slate-500 hover:text-slate-200'
          }`}
          title={`${item.label}: ${item.value || '未指定，点击补充'}`}
        >
          {isFilled ? (
            <CheckCircle2 className="w-3.5 h-3.5 text-sky-400 shrink-0" aria-hidden="true" />
          ) : (
            <PlusCircle className="w-3.5 h-3.5 text-slate-500 shrink-0" aria-hidden="true" />
          )}
          <span className="text-[11px] font-semibold text-slate-400">{item.label}:</span>
          <span className="max-w-[100px] truncate text-slate-200">
            {item.value || '待补充'}
          </span>
          <ChevronDown
            className={`w-3 h-3 text-slate-400 transition-transform ${
              isActive ? 'rotate-180 text-sky-400' : ''
            }`}
            aria-hidden="true"
          />
        </button>

        {/* 快捷选项气泡浮层 */}
        {isActive && (
          <div
            ref={popoverRef}
            className="absolute top-full left-0 mt-2 z-50 w-56 p-2 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl backdrop-blur-md animate-in fade-in zoom-in-95 duration-150"
          >
            <div className="flex items-center justify-between pb-1.5 mb-1.5 border-b border-slate-800 text-[11px] font-medium text-slate-400">
              <span>快捷选择 {item.label}</span>
              {isFilled && (
                <button
                  type="button"
                  onClick={() => { clearElementValue(item.key); }}
                  className="flex items-center text-rose-400 hover:text-rose-300"
                  title="清除此要素"
                >
                  <X className="w-3 h-3 mr-0.5" aria-hidden="true" />
                  <span>清除</span>
                </button>
              )}
            </div>

            <div className="space-y-1">
              {item.quickOptions.map((opt) => (
                <button
                  key={opt}
                  type="button"
                  onClick={() => { setElementValue(item.key, opt); }}
                  className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs transition-colors flex items-center justify-between ${
                    item.value === opt
                      ? 'bg-sky-600 text-white font-medium'
                      : 'text-slate-300 hover:bg-slate-800'
                  }`}
                >
                  <span className="truncate">{opt}</span>
                  {item.value === opt && (
                    <CheckCircle2 className="w-3 h-3 ml-1 shrink-0" aria-hidden="true" />
                  )}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-2.5 p-3 bg-slate-900/90 rounded-2xl border border-slate-800 shadow-lg select-none">
      {/* 左侧：五要素胶囊 */}
      <div className="flex flex-wrap items-center gap-1.5">
        <div className="flex items-center space-x-1 mr-1 text-xs font-semibold text-slate-300">
          <Compass className="w-3.5 h-3.5 text-indigo-400" aria-hidden="true" />
          <span>意图五要素:</span>
        </div>

        {keys.map((k) => renderCapsule(currentSpec[k]))}

        {/* 完整度得分标签 */}
        <span
          className={`text-[10px] px-2 py-0.5 rounded-full font-mono font-medium ${
            currentSpec.completenessScore >= 80
              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
              : currentSpec.completenessScore >= 40
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
          }`}
          title="设计意图完整度：要素越全，AI产出越精准"
        >
          完整度 {currentSpec.completenessScore}%
        </span>
      </div>

      {/* 右侧：Prompt 升华与多方向发散按钮 */}
      <div className="flex items-center space-x-2 shrink-0">
        <button
          type="button"
          onClick={() => { applyAssembledPrompt(); }}
          className="flex items-center space-x-1 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium border border-slate-700/80 transition-colors"
          title="将五要素自动组装为标准商业设计提示词"
        >
          <Wand2 className="w-3.5 h-3.5 text-sky-400" aria-hidden="true" />
          <span>升华提示词</span>
        </button>

        <button
          type="button"
          onClick={() => { generateVariants(); }}
          className="flex items-center space-x-1.5 px-3 py-1.5 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white rounded-lg text-xs font-semibold shadow-md shadow-indigo-950/40 transition-all hover:scale-[1.02] active:scale-[0.98]"
          title="一次性铺开 3 组差异化初稿方向供用户对比选型"
        >
          <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />
          <span>铺开 3 个方向初稿</span>
        </button>
      </div>
    </div>
  );
};
