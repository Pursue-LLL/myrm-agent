'use client';

import React, { useState } from 'react';
import {
  MousePointer,
  BoxSelect,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Download,
  Copy,
  Check,
  Zap,
} from 'lucide-react';
import { useInfiniteCanvasStore } from './useInfiniteCanvasStore';
import { exportLayersToSvg } from './canvasLayerEngine';

export const CanvasToolbarAndExportDeck: React.FC = () => {
  const [copied, setCopied] = useState(false);

  const {
    toolMode,
    setToolMode,
    viewport,
    zoomIn,
    zoomOut,
    resetZoom,
    layers,
    zeroTokenStats,
  } = useInfiniteCanvasStore();

  const handleExportSvg = () => {
    const svgContent = exportLayersToSvg(layers);
    const blob = new Blob([svgContent], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `myrm-structural-design-${Date.now()}.svg`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleCopySvg = () => {
    const svgContent = exportLayersToSvg(layers);
    navigator.clipboard.writeText(svgContent);
    setCopied(true);
    setTimeout(() => { setCopied(false); }, 1500);
  };

  return (
    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-40 flex items-center gap-3 px-4 py-2 rounded-2xl border border-slate-800 bg-slate-900/90 shadow-2xl backdrop-blur-md text-slate-200 select-none font-sans text-xs">
      {/* Tool Mode Buttons */}
      <div className="flex items-center gap-1 pr-3 border-r border-slate-800">
        <button
          type="button"
          aria-label="选择与移动工具"
          onClick={() => { setToolMode('select'); }}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-colors ${
            toolMode === 'select'
              ? 'bg-blue-600 text-white font-medium shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
          }`}
        >
          <MousePointer className="w-3.5 h-3.5" />
          选择/拖拽
        </button>

        <button
          type="button"
          aria-label="智能框选局部重绘工具"
          onClick={() => { setToolMode('lasso'); }}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-colors ${
            toolMode === 'lasso'
              ? 'bg-amber-600 text-white font-medium shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
          }`}
        >
          <BoxSelect className="w-3.5 h-3.5" />
          框选重绘
        </button>
      </div>

      {/* Zoom Controls */}
      <div className="flex items-center gap-1 pr-3 border-r border-slate-800 text-[11px] font-mono">
        <button
          type="button"
          aria-label="缩小画布"
          onClick={zoomOut}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
        >
          <ZoomOut className="w-3.5 h-3.5" />
        </button>
        <button
          type="button"
          aria-label="重置缩放"
          onClick={resetZoom}
          className="px-2 py-1 rounded-lg text-slate-300 hover:bg-slate-800 transition-colors"
        >
          {Math.round(viewport.zoom * 100)}%
        </button>
        <button
          type="button"
          aria-label="放大画布"
          onClick={zoomIn}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
        >
          <ZoomIn className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Zero Token Saving Badge */}
      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-950/80 border border-emerald-500/40 text-emerald-300 text-[11px]">
        <Zap className="w-3 h-3 text-amber-400 fill-amber-400" />
        <span>
          免 Token 直编: <strong className="text-white font-mono">{zeroTokenStats.inlineEditCount}</strong> 次
        </span>
        <span className="text-slate-400 text-[10px]">
          (省 ~{zeroTokenStats.estimatedSavedTokens.toLocaleString()} T)
        </span>
      </div>

      {/* Export Actions */}
      <div className="flex items-center gap-1.5 pl-1">
        <button
          type="button"
          onClick={handleCopySvg}
          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-medium transition-colors"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? '已复制 SVG' : '复制 SVG'}
        </button>

        <button
          type="button"
          onClick={handleExportSvg}
          className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-medium transition-colors shadow-md shadow-blue-500/20"
        >
          <Download className="w-3.5 h-3.5" />
          导出无损矢量
        </button>
      </div>
    </div>
  );
};
