import React from 'react';
import {
  Monitor,
  Play,
  Pause,
  RefreshCw,
  Share2,
  Key,
  Maximize2,
  Minimize2,
  Wifi,
  MousePointer,
  AlertCircle,
  ShieldCheck,
} from 'lucide-react';
import { useRemoteDesktopStore } from './useRemoteDesktopStore';

export const LiveDesktopCanvasViewport: React.FC = () => {
  const {
    connectionState,
    controlMode,
    sandboxId,
    streamMetrics,
    actionHistory,
    isExpanded,
    pauseStream,
    resumeStream,
    connectStream,
    openShareModal,
    requestHumanTakeover,
    releaseHumanTakeover,
    toggleExpanded,
  } = useRemoteDesktopStore();

  const isStreaming = connectionState === 'streaming';
  const isTakeover = controlMode === 'human-takeover';
  const latestAction = actionHistory[0];

  return (
    <section
      aria-label="沙箱远程桌面实时旁听视窗"
      className={`w-full bg-slate-950 border border-slate-800 rounded-xl overflow-hidden shadow-2xl text-slate-100 flex flex-col transition-all duration-300 ${
        isExpanded ? 'max-w-5xl mx-auto' : 'w-full'
      }`}
      data-testid="live-desktop-canvas-viewport"
    >
      {/* 视窗顶栏控制条 */}
      <header className="px-4 py-2.5 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center space-x-2.5">
          <div className="p-1.5 rounded-lg bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
            <Monitor className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-xs font-bold text-white tracking-tight">
                沙箱云电脑实时桌面
              </h2>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                {sandboxId}
              </span>
              <span
                className={`inline-flex items-center space-x-1 text-[10px] px-1.5 py-0.5 rounded font-medium ${
                  isStreaming
                    ? 'bg-emerald-950 text-emerald-300 border border-emerald-800/50'
                    : 'bg-amber-950 text-amber-300 border border-amber-800/50'
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    isStreaming ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'
                  }`}
                />
                <span>{isStreaming ? '低延迟推流中' : connectionState}</span>
              </span>
            </div>
          </div>
        </div>

        {/* 右侧性能指标与控制按钮 */}
        <div className="flex items-center space-x-2">
          {/* 流媒体遥测胶囊 */}
          <div className="hidden sm:flex items-center space-x-2 text-[10px] text-slate-400 bg-slate-950 px-2 py-1 rounded border border-slate-800 font-mono">
            <span className="flex items-center space-x-0.5">
              <Wifi className="w-2.5 h-2.5 text-emerald-400" />
              <span>{streamMetrics.latencyMs}ms</span>
            </span>
            <span>•</span>
            <span className="text-slate-300">{streamMetrics.fps} FPS</span>
            <span>•</span>
            <span>{streamMetrics.resolution}</span>
          </div>

          {/* 播放 / 暂停 */}
          {isStreaming ? (
            <button
              type="button"
              onClick={pauseStream}
              aria-label="暂停旁听画面"
              className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
            >
              <Pause className="w-3.5 h-3.5" />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => {
                if (connectionState === 'disconnected') {
                  connectStream();
                } else {
                  resumeStream();
                }
              }}
              aria-label="继续推流画面"
              className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
            </button>
          )}

          {/* 时效安全分享 */}
          <button
            type="button"
            onClick={openShareModal}
            aria-label="生成时效安全免登录分享链接"
            className="px-2.5 py-1 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded flex items-center space-x-1.5 transition-colors"
          >
            <Share2 className="w-3 h-3 text-indigo-400" />
            <span className="hidden md:inline">时效分享</span>
          </button>

          {/* 人工接管 */}
          {isTakeover ? (
            <button
              type="button"
              onClick={releaseHumanTakeover}
              aria-label="归还控制权给智能体"
              className="px-2.5 py-1 text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-white rounded flex items-center space-x-1.5 shadow"
            >
              <ShieldCheck className="w-3 h-3" />
              <span>交还控制权</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={() => requestHumanTakeover()}
              aria-label="请求人工介入接管操作"
              className="px-2.5 py-1 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded flex items-center space-x-1.5"
            >
              <Key className="w-3 h-3 text-amber-400" />
              <span className="hidden md:inline">人工接管</span>
            </button>
          )}

          {/* 全屏放大切换 */}
          <button
            type="button"
            onClick={toggleExpanded}
            aria-label={isExpanded ? '缩小视窗' : '放大视窗'}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
          >
            {isExpanded ? (
              <Minimize2 className="w-3.5 h-3.5" />
            ) : (
              <Maximize2 className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </header>

      {/* 桌面画面容器（模拟沙箱浏览器/桌面渲染） */}
      <div
        className="relative w-full aspect-video bg-slate-900 overflow-hidden flex flex-col justify-between"
        data-testid="desktop-stream-canvas"
      >
        {/* 顶部虚拟浏览器地址栏 */}
        <div className="w-full bg-slate-800/90 border-b border-slate-700/60 px-3 py-1.5 flex items-center space-x-2 text-[11px] text-slate-300">
          <div className="flex space-x-1">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500/80 inline-block" />
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80 inline-block" />
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80 inline-block" />
          </div>
          <div className="flex-1 bg-slate-950/60 rounded px-2.5 py-0.5 text-slate-400 font-mono text-[10px] truncate border border-slate-700/50">
            https://benchmark.enterprise.ai/portal/research/dashboard
          </div>
        </div>

        {/* 画面中间内容区 */}
        <div className="flex-1 p-6 relative flex flex-col items-center justify-center">
          {/* 模拟页面骨架 */}
          <div className="w-full max-w-lg bg-slate-950/50 rounded-lg p-4 border border-slate-800 space-y-3 opacity-80">
            <div className="h-4 bg-slate-800 rounded w-1/3 animate-pulse" />
            <div className="h-3 bg-slate-800/60 rounded w-full" />
            <div className="h-3 bg-slate-800/60 rounded w-4/5" />
            <div className="grid grid-cols-2 gap-2 pt-2">
              <div className="h-14 bg-slate-900 rounded border border-slate-800" />
              <div className="h-14 bg-slate-900 rounded border border-slate-800" />
            </div>
          </div>

          {/* 模拟 Agent 鼠标指针轨迹 */}
          {latestAction?.coordinates && (
            <div
              className="absolute pointer-events-none transition-all duration-300 flex items-center space-x-1"
              style={{
                left: `${(latestAction.coordinates.x / 1920) * 100}%`,
                top: `${(latestAction.coordinates.y / 1080) * 100}%`,
              }}
              data-testid="virtual-mouse-cursor"
            >
              <MousePointer className="w-4 h-4 text-amber-400 fill-amber-400 drop-shadow" />
              <span className="text-[9px] bg-amber-950/90 text-amber-300 px-1 py-0.5 rounded border border-amber-600/40">
                Agent CUA
              </span>
            </div>
          )}

          {/* 接管提示覆盖层 */}
          {isTakeover && (
            <div className="absolute top-4 right-4 bg-amber-950/90 border border-amber-500/50 text-amber-200 px-3 py-1.5 rounded-lg text-xs flex items-center space-x-2 shadow-lg animate-pulse">
              <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
              <span>人工接管激活中：您的鼠标与键盘已直接映射至远程沙箱</span>
            </div>
          )}
        </div>

        {/* 底部实时动作动态条 */}
        <footer className="w-full bg-slate-950/80 border-t border-slate-800/80 px-4 py-2 flex items-center justify-between text-xs text-slate-400">
          <div className="flex items-center space-x-2 truncate">
            <span className="font-semibold text-slate-300">当前执行：</span>
            <span className="text-slate-200 truncate">
              {latestAction ? latestAction.description : '等待指令调度中...'}
            </span>
          </div>
          <span className="text-[10px] text-slate-500 font-mono shrink-0 pl-2">
            断网零中断持续运行
          </span>
        </footer>
      </div>
    </section>
  );
};
