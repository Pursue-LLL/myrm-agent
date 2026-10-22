import React from 'react';
import {
  Columns2,
  Monitor,
  RefreshCw,
  Smartphone,
  Sparkles,
} from 'lucide-react';
import { useSandboxDualViewportStore } from './useSandboxDualViewportStore';
import { DualViewportDeviceFrame } from './DualViewportDeviceFrame';
import { ConsoleZeroToleranceHUD } from './ConsoleZeroToleranceHUD';
import { DesignSystemSnifferBadge } from './DesignSystemSnifferBadge';
import type { DualViewportMode } from './sandboxDualViewportTypes';

interface LiveSandboxDualViewportEngineProps {
  className?: string;
}

export const LiveSandboxDualViewportEngine: React.FC<LiveSandboxDualViewportEngineProps> = ({
  className = '',
}) => {
  const {
    activeMode,
    targetPreviewUrl,
    setActiveMode,
    setTargetPreviewUrl,
  } = useSandboxDualViewportStore();

  const handleModeChange = (mode: DualViewportMode): void => {
    setActiveMode(mode);
  };

  return (
    <section
      aria-label="沙箱双视口视觉自闭环验证与控制台自愈引擎"
      className={`relative flex h-full w-full flex-col bg-slate-950 text-slate-100 overflow-hidden ${className}`}
    >
      {/* 顶部控制台驾驶舱 */}
      <header
        aria-label="双视口验证顶栏"
        className="flex h-11 shrink-0 items-center justify-between border-b border-slate-800 bg-slate-900/80 px-4 backdrop-blur-md"
      >
        <div className="flex items-center gap-2.5">
          <div className="flex items-center gap-1.5 font-semibold text-xs text-white">
            <Sparkles className="w-4 h-4 text-indigo-400" />
            <span>沙箱双视口自闭环自愈引擎</span>
          </div>
          <span className="hidden sm:inline-block rounded bg-indigo-500/10 px-1.5 py-0.5 font-mono text-[10px] text-indigo-300 border border-indigo-500/20">
            Zero-Console-Error & Dual Viewport
          </span>
        </div>

        {/* 视口切换器 */}
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-lg bg-slate-800/80 p-0.5 border border-slate-700/60 text-xs">
            <button
              type="button"
              onClick={() => {
                handleModeChange('desktop');
              }}
              className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                activeMode === 'desktop'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              aria-label="切换至桌面端视口 (1280px)"
            >
              <Monitor className="w-3.5 h-3.5" />
              <span>桌面端</span>
            </button>
            <button
              type="button"
              onClick={() => {
                handleModeChange('mobile');
              }}
              className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                activeMode === 'mobile'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              aria-label="切换至移动端视口 (375px)"
            >
              <Smartphone className="w-3.5 h-3.5" />
              <span>移动端</span>
            </button>
            <button
              type="button"
              onClick={() => {
                handleModeChange('side_by_side');
              }}
              className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                activeMode === 'side_by_side'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              aria-label="切换至双视口并排对比模式"
            >
              <Columns2 className="w-3.5 h-3.5" />
              <span>双屏并排</span>
            </button>
          </div>
        </div>
      </header>

      {/* 前置设计系统与 API 契约嗅探看板 */}
      <DesignSystemSnifferBadge />

      {/* 设备外框与网页实时渲染主体 */}
      <main
        role="main"
        aria-label="双视口实时预览主舞台"
        className="relative flex flex-1 w-full overflow-hidden min-h-0"
      >
        <DualViewportDeviceFrame />
      </main>

      {/* 底部控制台与网络请求零容忍自愈 HUD */}
      <ConsoleZeroToleranceHUD />
    </section>
  );
};
