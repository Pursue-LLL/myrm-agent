import React, { useEffect, useRef } from 'react';
import {
  Camera,
  Gamepad2,
  RotateCcw,
  Activity,
  Terminal,
  Maximize2,
  Minimize2,
  ExternalLink,
} from 'lucide-react';
import { useThreeJsSandboxStore } from './useThreeJsSandboxStore';
import {
  buildThreeJsSandboxHtml,
  resolveCameraModeAction,
} from './threeJsSandboxEngine';
import { ThreeJsPerformancePanel } from './ThreeJsPerformancePanel';
import { ThreeJsConsoleDrawer } from './ThreeJsConsoleDrawer';
import { WebGLSelfHealingDossier } from './threeJsTypes';

interface ThreeJsCanvasViewerProps {
  onSelfHealingTriggered?: (dossier: WebGLSelfHealingDossier) => void;
  className?: string;
}

export const ThreeJsCanvasViewer: React.FC<ThreeJsCanvasViewerProps> = ({
  onSelfHealingTriggered,
  className = '',
}) => {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const {
    sceneTitle,
    sceneCode,
    viewportMode,
    cameraMode,
    logs,
    isConsoleOpen,
    isStatsOpen,
    setViewportMode,
    setCameraMode,
    updateMetrics,
    addLog,
    toggleConsole,
    toggleStats,
    triggerCameraReset,
  } = useThreeJsSandboxStore();

  const errorCount = logs.filter((l) => l.level === 'error').length;
  const modeAction = resolveCameraModeAction(cameraMode);

  // 监听来自沙箱 iframe 的跨域 postMessage 事件
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (!event.data || event.data.source !== 'threejs-sandbox') {
        return;
      }

      if (event.data.type === 'metrics') {
        updateMetrics(event.data.payload);
      } else if (event.data.type === 'log') {
        addLog(event.data.payload);
      }
    };

    window.addEventListener('message', handleMessage);
    return () => {
      window.removeEventListener('message', handleMessage);
    };
  }, [updateMetrics, addLog]);

  // 处理全屏与试玩 Pointer Lock
  const handleToggleFullscreen = () => {
    if (viewportMode === 'fullscreen') {
      setViewportMode('inline');
    } else {
      setViewportMode('fullscreen');
    }
  };

  const handlePointerLockPlay = () => {
    setCameraMode('pointer_lock');
    if (iframeRef.current && iframeRef.current.contentWindow) {
      iframeRef.current.contentWindow.focus();
    }
  };

  const handleOrbitCamera = () => {
    setCameraMode('orbit');
  };

  const containerClasses =
    viewportMode === 'fullscreen'
      ? 'fixed inset-0 z-50 bg-slate-950 flex flex-col'
      : viewportMode === 'pip'
      ? 'fixed bottom-4 right-4 z-40 w-96 h-64 shadow-2xl rounded-2xl overflow-hidden border border-slate-800 bg-slate-950 flex flex-col'
      : `relative w-full h-[520px] rounded-2xl overflow-hidden border border-slate-800 bg-slate-950 flex flex-col ${className}`;

  return (
    <section
      data-testid="threejs-canvas-viewer"
      aria-label="Three.js 交互式 3D 沙箱视窗"
      className={containerClasses}
    >
      {/* 顶部工具栏 */}
      <header className="flex items-center justify-between px-3.5 py-2.5 bg-slate-950/90 backdrop-blur border-b border-slate-800 z-10 text-xs">
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="font-semibold text-slate-200 truncate max-w-[200px]">
            {sceneTitle || 'Three.js 3D 渲染沙箱'}
          </span>
          <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-indigo-950/60 text-indigo-300 border border-indigo-800/60">
            WebGL 2.0
          </span>
        </div>

        {/* 控制器操作按钮组 */}
        <div className="flex items-center gap-1.5">
          {/* 相机模式切换 */}
          <div className="flex items-center bg-slate-900 border border-slate-800 rounded-xl p-0.5">
            <button
              type="button"
              onClick={handleOrbitCamera}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-lg transition-all ${
                cameraMode === 'orbit'
                  ? 'bg-indigo-600 text-white shadow-xs font-medium'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title="切换为自由观察轨道相机"
            >
              <Camera className="w-3 h-3" />
              <span>观察</span>
            </button>
            <button
              type="button"
              onClick={handlePointerLockPlay}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-lg transition-all ${
                cameraMode === 'pointer_lock'
                  ? 'bg-indigo-600 text-white shadow-xs font-medium'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title="切换为试玩操作模式（启用按键穿透与指针锁定）"
            >
              <Gamepad2 className="w-3 h-3" />
              <span>试玩</span>
            </button>
          </div>

          {/* 视角复位 */}
          <button
            type="button"
            onClick={triggerCameraReset}
            className="p-1.5 rounded-xl border border-slate-800 hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
            title="复位视角"
            aria-label="复位相机"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>

          {/* 性能面板开关 */}
          <button
            type="button"
            onClick={toggleStats}
            className={`p-1.5 rounded-xl border border-slate-800 transition-colors ${
              isStatsOpen
                ? 'bg-slate-800 text-indigo-400'
                : 'hover:bg-slate-800 text-slate-400 hover:text-slate-200'
            }`}
            title="切换渲染性能指标指示板"
            aria-label="性能面板"
          >
            <Activity className="w-3.5 h-3.5" />
          </button>

          {/* WebGL 控制台开关 */}
          <button
            type="button"
            onClick={toggleConsole}
            className={`relative p-1.5 rounded-xl border border-slate-800 transition-colors ${
              isConsoleOpen
                ? 'bg-slate-800 text-indigo-400'
                : 'hover:bg-slate-800 text-slate-400 hover:text-slate-200'
            }`}
            title="展开/收起 WebGL 运行时自检控制台"
            aria-label="控制台"
          >
            <Terminal className="w-3.5 h-3.5" />
            {errorCount > 0 && (
              <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-rose-500" />
            )}
          </button>

          {/* 画中画 / 全屏 */}
          <button
            type="button"
            onClick={() =>
              setViewportMode(viewportMode === 'pip' ? 'inline' : 'pip')
            }
            className="p-1.5 rounded-xl border border-slate-800 hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors hidden sm:inline-flex"
            title={viewportMode === 'pip' ? '还原窗口' : '画中画微缩视窗'}
            aria-label="画中画"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            onClick={handleToggleFullscreen}
            className="p-1.5 rounded-xl border border-slate-800 hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
            title={viewportMode === 'fullscreen' ? '退出全屏' : '全屏沉浸试玩'}
            aria-label="全屏"
          >
            {viewportMode === 'fullscreen' ? (
              <Minimize2 className="w-3.5 h-3.5" />
            ) : (
              <Maximize2 className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </header>

      {/* 核心渲染区 */}
      <div className="relative flex-1 w-full h-full bg-[#0b0f19] overflow-hidden">
        <ThreeJsPerformancePanel />

        <iframe
          ref={iframeRef}
          title={sceneTitle || 'Three.js Sandbox'}
          srcDoc={buildThreeJsSandboxHtml(sceneCode, sceneTitle)}
          sandbox="allow-scripts allow-pointer-lock allow-same-origin"
          className="w-full h-full border-none block"
        />

        {/* 底部操作指引胶囊 */}
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-10 pointer-events-none px-3 py-1 rounded-full bg-slate-950/70 backdrop-blur-md border border-slate-800 text-[11px] text-slate-400 select-none">
          <span>{modeAction.instruction}</span>
        </div>

        <ThreeJsConsoleDrawer onSelfHealingTriggered={onSelfHealingTriggered} />
      </div>
    </section>
  );
};
