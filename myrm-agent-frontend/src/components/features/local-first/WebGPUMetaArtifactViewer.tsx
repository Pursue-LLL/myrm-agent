import React, { useState } from 'react';
import {
  Activity,
  Box,
  Cpu,
  Layers,
  Maximize2,
  RotateCcw,
  Sparkles,
  Zap,
} from 'lucide-react';
import { WebGPURenderMode } from './localFirstTypes';
import { useLocalFirstStore } from './useLocalFirstStore';

interface WebGPUMetaArtifactViewerProps {
  className?: string;
  onSceneReload?: () => void;
}

export const WebGPUMetaArtifactViewer: React.FC<
  WebGPUMetaArtifactViewerProps
> = ({ className = '', onSceneReload }) => {
  const sceneConfig = useLocalFirstStore((state) => state.sceneConfig);
  const updateSceneConfig = useLocalFirstStore(
    (state) => state.updateSceneConfig,
  );

  const [activeTab, setActiveTab] = useState<'viewport' | 'nodes' | 'stats'>(
    'viewport',
  );

  const toggleRenderMode = () => {
    const nextMode: WebGPURenderMode =
      sceneConfig.renderMode === 'webgpu_3d'
        ? 'canvas_2d_fallback'
        : 'webgpu_3d';
    updateSceneConfig({
      renderMode: nextMode,
      isHardwareAccelerated: nextMode === 'webgpu_3d',
    });
  };

  const handleReset = () => {
    updateSceneConfig({
      nodesCount: 12,
      status: 'ready',
    });
    if (onSceneReload) {
      onSceneReload();
    }
  };

  return (
    <div
      data-testid="webgpu-meta-artifact-viewer"
      className={`my-3 w-full max-w-xl rounded-xl border border-primary/20 bg-background/95 p-4 text-xs shadow-md backdrop-blur-md dark:bg-muted/30 ${className}`}
    >
      {/* 头部标题与渲染引擎微标 */}
      <div className="flex items-start justify-between gap-2 border-b border-border/40 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-500">
            <Box className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-semibold text-foreground text-sm">
                WebGPU 模块化工件画布
              </span>
              <span className="rounded bg-indigo-500/15 px-1.5 py-0.5 text-[10px] font-medium text-indigo-600 dark:text-indigo-400">
                {sceneConfig.renderMode === 'webgpu_3d'
                  ? 'WebGPU 3D 加速'
                  : '2D Canvas 降级'}
              </span>
            </div>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              Core / Viewer / Editor / Nodes 分层渲染体系 · 客户端即时物理交互
            </p>
          </div>
        </div>

        {/* 顶部控制操作 */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={toggleRenderMode}
            aria-label="切换渲染引擎模式"
            className="flex items-center gap-1 rounded-md border border-border/60 bg-muted/20 px-2 py-1 text-[11px] text-foreground hover:bg-muted/50 transition-colors"
          >
            <Cpu className="h-3 w-3 text-primary" />
            <span>切换模式</span>
          </button>

          <button
            type="button"
            onClick={handleReset}
            aria-label="重置画布场景"
            className="rounded-md border border-border/60 p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* 视图选项卡与状态栏 */}
      <div className="mt-3 flex items-center justify-between border-b border-border/30 pb-2 text-[11px]">
        <div className="flex items-center gap-1">
          {(['viewport', 'nodes', 'stats'] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => {
                setActiveTab(tab);
              }}
              className={`rounded-md px-2.5 py-0.5 transition-colors ${
                activeTab === tab
                  ? 'bg-primary text-primary-foreground font-semibold'
                  : 'text-muted-foreground hover:bg-muted/50'
              }`}
            >
              {tab === 'viewport' && '视口画布'}
              {tab === 'nodes' && '场景节点树'}
              {tab === 'stats' && '硬件指标'}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          <span>节点数: {sceneConfig.nodesCount}</span>
          <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
            <Activity className="h-2.5 w-2.5 animate-pulse" />
            <span>60 FPS</span>
          </span>
        </div>
      </div>

      {/* 画布视口区域 */}
      {activeTab === 'viewport' && (
        <div className="mt-3 flex h-48 w-full flex-col items-center justify-center rounded-xl border border-dashed border-border/70 bg-radial from-background via-muted/10 to-muted/30 p-4 text-center">
          <Box className="h-8 w-8 text-indigo-500/60 animate-bounce" />
          <span className="mt-2 text-xs font-semibold text-foreground">
            {sceneConfig.renderMode === 'webgpu_3d'
              ? 'WebGPU 3D 渲染管线已挂载'
              : '2D Canvas 平滑降级视口已挂载'}
          </span>
          <p className="mt-1 max-w-xs text-[11px] text-muted-foreground leading-tight">
            支持视锥体剔除、动态着色器变换与节点指针交互
          </p>
        </div>
      )}

      {/* 节点树区域 */}
      {activeTab === 'nodes' && (
        <div className="mt-3 max-h-48 space-y-1.5 overflow-y-auto rounded-xl border border-border/50 bg-muted/10 p-3 font-mono text-[11px]">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="flex items-center justify-between rounded-md border border-border/30 bg-background/80 p-2"
            >
              <div className="flex items-center gap-2">
                <Layers className="h-3.5 w-3.5 text-primary" />
                <span className="text-foreground">
                  Node_MeshGroup_0{i + 1}
                </span>
              </div>
              <span className="text-[10px] text-muted-foreground">
                顶点数: {(i + 1) * 240}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* 硬件指标区域 */}
      {activeTab === 'stats' && (
        <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
          <div className="rounded-lg border border-border/50 bg-background/60 p-2.5">
            <span className="text-muted-foreground">着色器后端</span>
            <span className="mt-1 block font-mono font-semibold text-foreground">
              {sceneConfig.renderMode === 'webgpu_3d' ? 'WGSL / SPIR-V' : 'Canvas2D Context'}
            </span>
          </div>
          <div className="rounded-lg border border-border/50 bg-background/60 p-2.5">
            <span className="text-muted-foreground">硬件加速状态</span>
            <span className="mt-1 block font-mono font-semibold text-emerald-600 dark:text-emerald-400">
              {sceneConfig.isHardwareAccelerated ? 'GPU Accelerated' : 'Software Fallback'}
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
