'use client';

import React from 'react';
import {
  Lock,
  Unlock,
  Palette,
  LayoutGrid,
  Play,
  GitFork,
  ZoomIn,
  ZoomOut,
  RotateCcw,
} from 'lucide-react';
import { useMultiArtboardStore } from './useMultiArtboardStore';

const THEME_PRESETS = [
  {
    name: 'Neo-Clean Indigo',
    primaryColor: '#6366f1',
    secondaryColor: '#4f46e5',
    backgroundColor: '#0f172a',
    borderRadius: 16,
    fontFamily: 'Inter, system-ui, sans-serif',
  },
  {
    name: 'Cyber Emerald',
    primaryColor: '#10b981',
    secondaryColor: '#059669',
    backgroundColor: '#022c22',
    borderRadius: 8,
    fontFamily: 'JetBrains Mono, monospace',
  },
  {
    name: 'Sunset Amber',
    primaryColor: '#f59e0b',
    secondaryColor: '#d97706',
    backgroundColor: '#1c1917',
    borderRadius: 20,
    fontFamily: 'Plus Jakarta Sans, sans-serif',
  },
  {
    name: 'Rose Quartz',
    primaryColor: '#f43f5e',
    secondaryColor: '#e11d48',
    backgroundColor: '#18181b',
    borderRadius: 24,
    fontFamily: 'Poppins, sans-serif',
  },
];

export const CrossArtboardThemeLockBar: React.FC = () => {
  const {
    themeLock,
    showFlowLinks,
    viewport,
    updateThemeLock,
    toggleThemeLock,
    toggleFlowLinks,
    arrangeArtboardsGrid,
    setViewportZoom,
    resetViewport,
    startPlayback,
  } = useMultiArtboardStore();

  const handleSelectPreset = (preset: (typeof THEME_PRESETS)[0]) => {
    updateThemeLock({
      presetName: preset.name,
      primaryColor: preset.primaryColor,
      secondaryColor: preset.secondaryColor,
      backgroundColor: preset.backgroundColor,
      borderRadius: preset.borderRadius,
      fontFamily: preset.fontFamily,
    });
  };

  return (
    <div className="absolute top-4 left-4 right-4 z-30 flex items-center justify-between pointer-events-none">
      {/* 左侧：视觉风格一致性锁与调色板 */}
      <div className="flex items-center space-x-2 bg-slate-900/90 backdrop-blur-md px-3.5 py-2 rounded-xl border border-slate-800 shadow-xl pointer-events-auto">
        <button
          type="button"
          onClick={() => { toggleThemeLock(); }}
          className={`flex items-center space-x-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
            themeLock.isLocked
              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 hover:bg-amber-500/30'
              : 'bg-slate-800 text-slate-400 hover:text-slate-200'
          }`}
          title={themeLock.isLocked ? '视觉风格已锁定：多画板继承统一规范' : '点击锁定风格'}
        >
          {themeLock.isLocked ? (
            <Lock className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" />
          ) : (
            <Unlock className="w-3.5 h-3.5" aria-hidden="true" />
          )}
          <span>{themeLock.isLocked ? '风格锁激活' : '风格未锁定'}</span>
        </button>

        <div className="h-4 w-px bg-slate-800" />

        <div className="flex items-center space-x-1.5 text-xs text-slate-300">
          <Palette className="w-3.5 h-3.5 text-indigo-400" aria-hidden="true" />
          <span className="hidden sm:inline font-medium">设计预设:</span>
          <select
            value={themeLock.presetName}
            onChange={(e) => {
              const matched = THEME_PRESETS.find((p) => p.name === e.target.value);
              if (matched) {
                handleSelectPreset(matched);
              }
            }}
            aria-label="选择全局设计风格预设"
            className="bg-slate-800 text-slate-200 text-xs rounded-md border border-slate-700 px-2 py-1 outline-none focus:border-indigo-500 cursor-pointer"
          >
            {THEME_PRESETS.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
              </option>
            ))}
          </select>
        </div>

        {/* 动态主色快速调整 */}
        <div className="flex items-center space-x-1 ml-1">
          <label htmlFor="primary-color-picker" className="sr-only">主色微调</label>
          <input
            id="primary-color-picker"
            type="color"
            value={themeLock.primaryColor}
            onChange={(e) => { updateThemeLock({ primaryColor: e.target.value }); }}
            className="w-5 h-5 rounded cursor-pointer border-0 bg-transparent"
            title="微调全局主色"
          />
        </div>
      </div>

      {/* 右侧：多画板排列整理、连线显隐、缩放控制与播放演示入口 */}
      <div className="flex items-center space-x-2 bg-slate-900/90 backdrop-blur-md px-3.5 py-2 rounded-xl border border-slate-800 shadow-xl pointer-events-auto">
        <button
          type="button"
          onClick={() => { arrangeArtboardsGrid(4); }}
          className="flex items-center space-x-1.5 px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium transition-colors"
          title="一键网格阵列排布所有画板"
        >
          <LayoutGrid className="w-3.5 h-3.5 text-sky-400" aria-hidden="true" />
          <span className="hidden md:inline">全景平铺整理</span>
        </button>

        <button
          type="button"
          onClick={() => { toggleFlowLinks(); }}
          className={`flex items-center space-x-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            showFlowLinks
              ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
              : 'bg-slate-800 text-slate-400 hover:text-slate-200'
          }`}
          title="切换是否显示画板间交互流转连线"
        >
          <GitFork className="w-3.5 h-3.5 text-sky-400" aria-hidden="true" />
          <span className="hidden md:inline">流转连线</span>
        </button>

        <div className="h-4 w-px bg-slate-800" />

        {/* 缩放按钮 */}
        <div className="flex items-center space-x-1 text-slate-300">
          <button
            type="button"
            onClick={() => { setViewportZoom(viewport.zoom - 0.1); }}
            className="p-1 hover:bg-slate-800 rounded transition-colors"
            title="缩小"
          >
            <ZoomOut className="w-3.5 h-3.5" aria-hidden="true" />
          </button>
          <span className="text-[11px] font-mono w-10 text-center">
            {Math.round(viewport.zoom * 100)}%
          </span>
          <button
            type="button"
            onClick={() => { setViewportZoom(viewport.zoom + 0.1); }}
            className="p-1 hover:bg-slate-800 rounded transition-colors"
            title="放大"
          >
            <ZoomIn className="w-3.5 h-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={resetViewport}
            className="p-1 hover:bg-slate-800 rounded transition-colors"
            title="重置缩放"
          >
            <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
          </button>
        </div>

        <div className="h-4 w-px bg-slate-800" />

        {/* 核心亮点：免 Token 原型播放演示 */}
        <button
          type="button"
          onClick={() => { startPlayback(); }}
          className="flex items-center space-x-1.5 px-3 py-1.5 bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 text-white rounded-lg text-xs font-semibold shadow-lg shadow-emerald-950/40 transition-all hover:scale-[1.02] active:scale-[0.98]"
          title="免 Token 原型全真交互演示走查"
        >
          <Play className="w-3.5 h-3.5 fill-current" aria-hidden="true" />
          <span>播放演示</span>
          <span className="text-[10px] bg-emerald-800/80 px-1.5 py-0.5 rounded text-emerald-200 ml-1">
            0 Token
          </span>
        </button>
      </div>
    </div>
  );
};
