/**
 * InteractiveArtifactSandbox.tsx
 * 独立实时运行交互沙盒面板：安全 iframe 隔离运行、全屏切换与视口多端自适应
 */

import React, { useMemo, useState } from 'react';
import {
  Maximize2,
  Minimize2,
  Monitor,
  Play,
  RotateCw,
  Smartphone,
  Tablet,
} from 'lucide-react';
import { buildSafeSandboxIframeSrcDoc } from './artifactSandboxEngine';
import { useArtifactSandboxStore } from './useArtifactSandboxStore';

export interface InteractiveArtifactSandboxProps {
  className?: string;
  onReload?: () => void;
  onFullscreenChange?: (isFullscreen: boolean) => void;
}

type ViewportMode = 'desktop' | 'tablet' | 'mobile';

const viewportWidthMap: Record<ViewportMode, string> = {
  desktop: 'w-full',
  tablet: 'w-[768px]',
  mobile: 'w-[375px]',
};

export const InteractiveArtifactSandbox: React.FC<
  InteractiveArtifactSandboxProps
> = ({ className = '', onReload, onFullscreenChange }) => {
  const activeArtifact = useArtifactSandboxStore((state) => state.activeArtifact);
  const isFullscreen = useArtifactSandboxStore((state) => state.isFullscreen);
  const toggleFullscreen = useArtifactSandboxStore(
    (state) => state.toggleFullscreen
  );

  const [viewportMode, setViewportMode] = useState<ViewportMode>('desktop');
  const [reloadKey, setReloadKey] = useState(0);

  const safeSrcDoc = useMemo(() => {
    const raw = activeArtifact?.rawContent ?? '<h1>就绪沙盒</h1><p>无内容工件</p>';
    return buildSafeSandboxIframeSrcDoc(raw);
  }, [activeArtifact]);

  const handleReload = (): void => {
    setReloadKey((prev) => prev + 1);
    if (onReload !== undefined) {
      onReload();
    }
  };

  const handleToggleFullscreen = (): void => {
    const next = !isFullscreen;
    toggleFullscreen(next);
    if (onFullscreenChange !== undefined) {
      onFullscreenChange(next);
    }
  };

  return (
    <section
      data-testid="interactive-artifact-sandbox"
      aria-label="工件独立交互沙盒"
      className={`flex flex-col bg-slate-900 border border-slate-700/80 rounded-2xl shadow-xl overflow-hidden ${
        isFullscreen ? 'fixed inset-0 z-50 rounded-none' : 'w-full h-[540px]'
      } ${className}`}
    >
      {/* 顶部控制栏 */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-950/80 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <Play className="w-4 h-4 text-emerald-400" />
          <span className="text-xs font-semibold text-slate-200">
            {activeArtifact?.title ?? '互动沙盒预览'}
          </span>
          <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-800/60">
            安全隔离
          </span>
        </div>

        {/* 视口切换器 */}
        <div className="flex items-center gap-1 bg-slate-900 p-0.5 rounded-lg border border-slate-800">
          <button
            type="button"
            data-testid="viewport-desktop-btn"
            aria-label="切换至桌面视口"
            onClick={() => setViewportMode('desktop')}
            className={`p-1 rounded text-xs transition-colors ${
              viewportMode === 'desktop'
                ? 'bg-blue-600 text-white'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Monitor className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            data-testid="viewport-tablet-btn"
            aria-label="切换至平板视口"
            onClick={() => setViewportMode('tablet')}
            className={`p-1 rounded text-xs transition-colors ${
              viewportMode === 'tablet'
                ? 'bg-blue-600 text-white'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Tablet className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            data-testid="viewport-mobile-btn"
            aria-label="切换至手机视口"
            onClick={() => setViewportMode('mobile')}
            className={`p-1 rounded text-xs transition-colors ${
              viewportMode === 'mobile'
                ? 'bg-blue-600 text-white'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Smartphone className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* 动作区 */}
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            data-testid="sandbox-reload-btn"
            aria-label="重新载入沙盒"
            onClick={handleReload}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
            title="重新运行当前沙盒代码"
          >
            <RotateCw className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            data-testid="sandbox-fullscreen-btn"
            aria-label={isFullscreen ? '退出全屏' : '全屏显示'}
            onClick={handleToggleFullscreen}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            {isFullscreen ? (
              <Minimize2 className="w-3.5 h-3.5" />
            ) : (
              <Maximize2 className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* 沙盒 iframe 容器 */}
      <div className="flex-1 bg-slate-950 flex items-center justify-center p-2 overflow-auto">
        <iframe
          key={reloadKey}
          data-testid="sandbox-runtime-iframe"
          title="沙盒代码实时执行渲染"
          srcDoc={safeSrcDoc}
          sandbox="allow-scripts"
          className={`h-full bg-white rounded-lg shadow-inner border border-slate-800 transition-all duration-300 ${viewportWidthMap[viewportMode]}`}
        />
      </div>
    </section>
  );
};
