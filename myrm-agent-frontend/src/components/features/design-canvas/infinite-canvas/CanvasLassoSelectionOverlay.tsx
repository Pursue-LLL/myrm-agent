'use client';

import React, { useState } from 'react';
import {
  Sparkles,
  Lock,
  Send,
  X,
  Layers,
  CheckCircle2,
} from 'lucide-react';
import { useInfiniteCanvasStore } from './useInfiniteCanvasStore';

export const CanvasLassoSelectionOverlay: React.FC = () => {
  const [inpaintingPrompt, setInpaintingPrompt] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const {
    activeLassoBox,
    lassoInpaintingContext,
    setLassoBox,
    submitLassoInpainting,
    viewport,
  } = useInfiniteCanvasStore();

  if (!activeLassoBox || !lassoInpaintingContext) {
    return null;
  }

  const { selectedBox, targetLayerIds, lockedLayerIds } = lassoInpaintingContext;

  // 将画布选区坐标映射至视口屏幕坐标
  const screenLeft = selectedBox.startX * viewport.zoom + viewport.panX;
  const screenTop = selectedBox.endY * viewport.zoom + viewport.panY + 12;

  const handleSubmit = () => {
    if (!inpaintingPrompt.trim()) {
      return;
    }
    submitLassoInpainting(inpaintingPrompt.trim());
    setSubmitted(true);
    setTimeout(() => {
      setSubmitted(false);
      setLassoBox(null);
      setInpaintingPrompt('');
    }, 1200);
  };

  return (
    <div
      style={{
        position: 'absolute',
        left: `${Math.max(16, screenLeft)}px`,
        top: `${Math.max(16, screenTop)}px`,
        zIndex: 50,
      }}
      className="w-80 rounded-xl border border-amber-500/50 bg-slate-900/95 p-3.5 shadow-2xl backdrop-blur-md text-slate-200 font-sans select-none animate-in fade-in zoom-in-95 duration-200"
    >
      {/* Header */}
      <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-xs">
        <div className="flex items-center gap-1.5 font-semibold text-amber-300">
          <Sparkles className="w-3.5 h-3.5" />
          智能局部重绘 (Inpainting)
        </div>
        <button
          type="button"
          aria-label="清除选区"
          onClick={() => { setLassoBox(null); }}
          className="rounded p-0.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Layer Stats */}
      <div className="mt-2.5 flex items-center justify-between text-[11px] text-slate-400">
        <span className="flex items-center gap-1">
          <Layers className="w-3 h-3 text-sky-400" />
          重绘目标: <strong className="text-slate-200 font-medium">{targetLayerIds.length} 个图层</strong>
        </span>
        <span className="flex items-center gap-1 text-emerald-400">
          <Lock className="w-3 h-3" />
          {lockedLayerIds.length} 个图层已锁定
        </span>
      </div>

      {/* Inpainting Prompt Input */}
      {submitted ? (
        <div className="mt-3 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-emerald-950/60 text-emerald-300 text-xs border border-emerald-500/40">
          <CheckCircle2 className="w-4 h-4" />
          局部重绘上下文已反向注入对话！
        </div>
      ) : (
        <div className="mt-3 space-y-2">
          <input
            type="text"
            aria-label="输入局部重绘调整要求"
            placeholder="输入局部修改要求，例如'换成左右双栏'..."
            value={inpaintingPrompt}
            onChange={(e) => { setInpaintingPrompt(e.target.value); }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                handleSubmit();
              }
            }}
            className="w-full text-xs px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-amber-500"
          />
          <button
            type="button"
            onClick={handleSubmit}
            className="w-full py-1.5 px-3 rounded-lg bg-amber-600 hover:bg-amber-500 text-slate-950 font-semibold text-xs transition-colors flex items-center justify-center gap-1.5 shadow-md shadow-amber-600/20"
          >
            <Send className="w-3.5 h-3.5" />
            注入选区上下文并微调
          </button>
        </div>
      )}
    </div>
  );
};
