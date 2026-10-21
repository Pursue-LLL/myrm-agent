import React from 'react';
import { Smartphone, Monitor, RefreshCw, ExternalLink } from 'lucide-react';
import { useSandboxDualViewportStore } from './useSandboxDualViewportStore';
import type { DualViewportMode } from './sandboxDualViewportTypes';

interface DualViewportDeviceFrameProps {
  className?: string;
}

export const DualViewportDeviceFrame: React.FC<DualViewportDeviceFrameProps> = ({
  className = '',
}) => {
  const {
    activeMode,
    targetPreviewUrl,
    isLiveReloading,
  } = useSandboxDualViewportStore();

  const renderMobileFrame = (): React.ReactElement => {
    return (
      <section
        aria-label="移动端视口预览 (375x667)"
        className="flex flex-col items-center justify-start shrink-0"
      >
        <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-2">
          <Smartphone className="w-3.5 h-3.5 text-indigo-400" />
          <span className="font-mono text-[11px]">Mobile 375×667 (iPhone SE/Mini)</span>
        </div>

        {/* 拟真手机外壳 */}
        <div className="relative w-[375px] h-[667px] rounded-[36px] border-4 border-slate-700 bg-slate-900 shadow-2xl overflow-hidden flex flex-col">
          {/* 手机顶部微刘海与听筒 */}
          <div className="h-6 w-full bg-slate-800/90 flex items-center justify-center shrink-0 border-b border-slate-700/50">
            <div className="w-12 h-1 bg-slate-600 rounded-full" />
          </div>

          {/* 视口内容区域 */}
          <div className="relative flex-1 bg-slate-950 overflow-hidden">
            <iframe
              src={targetPreviewUrl}
              title="沙箱移动端实时渲染视图"
              className="w-full h-full border-0 select-none"
              sandbox="allow-scripts allow-same-origin allow-forms"
            />
          </div>

          {/* 手机底部 Home Indicator */}
          <div className="h-4 w-full bg-slate-900 flex items-center justify-center shrink-0">
            <div className="w-24 h-1 bg-slate-600 rounded-full" />
          </div>
        </div>
      </section>
    );
  };

  const renderDesktopFrame = (): React.ReactElement => {
    return (
      <section
        aria-label="桌面端视口预览 (1280x800)"
        className="flex flex-1 flex-col items-center justify-start min-w-0 h-full"
      >
        <div className="flex items-center justify-between w-full max-w-5xl px-2 text-xs text-slate-400 mb-2">
          <div className="flex items-center gap-1.5">
            <Monitor className="w-3.5 h-3.5 text-sky-400" />
            <span className="font-mono text-[11px]">Desktop 1280×800 (Standard Mac/PC)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-slate-500 font-mono">{targetPreviewUrl}</span>
            <a
              href={targetPreviewUrl}
              target="_blank"
              rel="noreferrer"
              className="text-slate-400 hover:text-slate-200"
              title="新窗口全屏打开沙箱端口"
            >
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>

        {/* 拟真桌面浏览器外壳 */}
        <div className="relative w-full max-w-5xl flex-1 rounded-xl border border-slate-800 bg-slate-900 shadow-2xl overflow-hidden flex flex-col">
          {/* 浏览器顶栏地址模拟 */}
          <div className="h-8 w-full bg-slate-850 px-3 flex items-center gap-2 border-b border-slate-800 shrink-0">
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500/80" />
              <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
            </div>

            <div className="flex-1 max-w-md mx-auto bg-slate-950/80 border border-slate-800 rounded px-2.5 py-0.5 text-[11px] font-mono text-slate-400 flex items-center justify-between">
              <span className="truncate">{targetPreviewUrl}</span>
              {isLiveReloading && (
                <RefreshCw className="w-2.5 h-2.5 animate-spin text-sky-400" />
              )}
            </div>
          </div>

          {/* 桌面端内容容器 */}
          <div className="relative flex-1 bg-slate-950 overflow-hidden">
            <iframe
              src={targetPreviewUrl}
              title="沙箱桌面端实时渲染视图"
              className="w-full h-full border-0 select-none"
              sandbox="allow-scripts allow-same-origin allow-forms"
            />
          </div>
        </div>
      </section>
    );
  };

  return (
    <div
      className={`relative flex flex-1 w-full h-full p-4 overflow-auto bg-slate-950 justify-center gap-6 ${className}`}
    >
      {(activeMode === 'mobile' || activeMode === 'side_by_side') && (
        renderMobileFrame()
      )}
      {(activeMode === 'desktop' || activeMode === 'side_by_side') && (
        renderDesktopFrame()
      )}
    </div>
  );
};
