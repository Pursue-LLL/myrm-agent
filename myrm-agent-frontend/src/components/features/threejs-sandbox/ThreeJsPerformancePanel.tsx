import React from 'react';
import { Activity, Gauge, Layers, Box, Image as ImageIcon } from 'lucide-react';
import { useThreeJsSandboxStore } from './useThreeJsSandboxStore';

export const ThreeJsPerformancePanel: React.FC = () => {
  const { metrics, isStatsOpen } = useThreeJsSandboxStore();

  if (!isStatsOpen) {
    return null;
  }

  const getFpsColor = (fps: number) => {
    if (fps >= 55) {
      return 'text-emerald-400';
    }
    if (fps >= 30) {
      return 'text-amber-400';
    }
    return 'text-rose-400';
  };

  return (
    <aside
      data-testid="threejs-performance-panel"
      aria-label="WebGL 渲染性能监视面板"
      className="absolute top-3 left-3 z-20 pointer-events-none select-none bg-slate-950/80 backdrop-blur-md border border-slate-800/90 rounded-xl px-3 py-2 text-xs shadow-xl min-w-[160px]"
    >
      <div className="flex items-center gap-1.5 pb-1.5 mb-1.5 border-b border-slate-800 text-[11px] font-semibold text-slate-300">
        <Activity className="w-3.5 h-3.5 text-indigo-400" />
        <span>渲染引擎状态</span>
      </div>

      <div className="space-y-1 font-mono text-[11px]">
        {/* FPS */}
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1 text-slate-400">
            <Gauge className="w-3 h-3 text-slate-500" />
            <span>帧率 (FPS)</span>
          </span>
          <span className={`font-bold ${getFpsColor(metrics.fps)}`}>
            {metrics.fps}
          </span>
        </div>

        {/* Draw Calls */}
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1 text-slate-400">
            <Layers className="w-3 h-3 text-slate-500" />
            <span>Draw Calls</span>
          </span>
          <span className="text-slate-200">{metrics.drawCalls}</span>
        </div>

        {/* 三角面数 */}
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1 text-slate-400">
            <Box className="w-3 h-3 text-slate-500" />
            <span>三角形</span>
          </span>
          <span className="text-slate-200">
            {metrics.triangles.toLocaleString()}
          </span>
        </div>

        {/* 纹理 / 几何体 */}
        <div className="flex items-center justify-between pt-0.5 border-t border-slate-900 text-[10px] text-slate-500">
          <span className="flex items-center gap-1">
            <ImageIcon className="w-2.5 h-2.5" />
            <span>纹理: {metrics.textures}</span>
          </span>
          <span>几何体: {metrics.geometries}</span>
        </div>
      </div>
    </aside>
  );
};
