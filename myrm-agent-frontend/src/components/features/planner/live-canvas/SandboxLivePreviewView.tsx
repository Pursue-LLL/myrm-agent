/**
 * Sandbox Live Preview View
 * 智能体交付物沙箱即时预览视窗与多视口响应式调试器
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. iframe 安全沙箱限制（sandbox="allow-scripts allow-same-origin"）；
 * 5. 行数严格受控在 400 行以内。
 */

import React, { useMemo } from 'react';
import {
  ExternalLink,
  Laptop,
  Maximize2,
  RefreshCw,
  Smartphone,
  Tablet,
} from 'lucide-react';
import { SandboxViewportMode } from './plannerCanvasTypes';
import { usePlannerCanvasStore } from './usePlannerCanvasStore';

export interface SandboxLivePreviewViewProps {
  className?: string;
}

export const SandboxLivePreviewView: React.FC<SandboxLivePreviewViewProps> = ({
  className = '',
}) => {
  const {
    viewportMode,
    sandboxReloadKey,
    setViewportMode,
    triggerSandboxReload,
    getActiveArtifact,
    getSelectedNode,
  } = usePlannerCanvasStore();

  const artifact = getActiveArtifact();
  const selectedNode = getSelectedNode();

  const getViewportWidth = (mode: SandboxViewportMode): string => {
    if (mode === 'mobile') {
      return '375px';
    }
    if (mode === 'tablet') {
      return '768px';
    }
    return '100%';
  };

  const iframeSrcDoc = useMemo(() => {
    if (!artifact) {
      return undefined;
    }
    if (artifact.rawContent) {
      return artifact.rawContent;
    }
    return `<!DOCTYPE html><html><body style="background:#09090b;color:#a1a1aa;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;"><h3>产物准备中...</h3></body></html>`;
  }, [artifact]);

  const handleOpenInNewTab = (): void => {
    if (artifact?.rawContent) {
      const blob = new Blob([artifact.rawContent], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
    }
  };

  return (
    <div
      data-testid="sandbox-live-preview-view"
      className={`flex flex-col rounded-lg border border-neutral-800 bg-neutral-950 text-neutral-100 ${className}`}
    >
      {/* 视口与沙箱控制顶部栏 */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-800/80 bg-neutral-900/60 px-3.5 py-2 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-medium text-neutral-300">
            {artifact ? artifact.title : '沙箱预览'}
          </span>
          {selectedNode && (
            <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] text-neutral-400">
              关联: {selectedNode.title}
            </span>
          )}
        </div>

        {/* 视口模式切换组 */}
        <div className="flex items-center gap-1 rounded-md border border-neutral-800 bg-neutral-900 p-0.5">
          <button
            type="button"
            onClick={() => {
              setViewportMode('desktop');
            }}
            data-testid="viewport-btn-desktop"
            className={`flex items-center gap-1 rounded px-2 py-1 text-[11px] transition-colors ${
              viewportMode === 'desktop'
                ? 'bg-indigo-950 font-medium text-indigo-300'
                : 'text-neutral-400 hover:text-neutral-200'
            }`}
            title="桌面端视口 (100%)"
          >
            <Laptop className="h-3 w-3" />
            <span className="hidden sm:inline">Desktop</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setViewportMode('tablet');
            }}
            data-testid="viewport-btn-tablet"
            className={`flex items-center gap-1 rounded px-2 py-1 text-[11px] transition-colors ${
              viewportMode === 'tablet'
                ? 'bg-indigo-950 font-medium text-indigo-300'
                : 'text-neutral-400 hover:text-neutral-200'
            }`}
            title="平板端视口 (768px)"
          >
            <Tablet className="h-3 w-3" />
            <span className="hidden sm:inline">Tablet</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setViewportMode('mobile');
            }}
            data-testid="viewport-btn-mobile"
            className={`flex items-center gap-1 rounded px-2 py-1 text-[11px] transition-colors ${
              viewportMode === 'mobile'
                ? 'bg-indigo-950 font-medium text-indigo-300'
                : 'text-neutral-400 hover:text-neutral-200'
            }`}
            title="手机端视口 (375px)"
          >
            <Smartphone className="h-3 w-3" />
            <span className="hidden sm:inline">Mobile</span>
          </button>
        </div>

        {/* 刷新与外部打开 */}
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={triggerSandboxReload}
            data-testid="reload-sandbox-btn"
            className="rounded p-1 text-neutral-400 hover:bg-neutral-800 hover:text-neutral-200"
            title="重载沙箱运行态"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>

          {artifact && (
            <button
              type="button"
              onClick={handleOpenInNewTab}
              data-testid="open-sandbox-external-btn"
              className="rounded p-1 text-neutral-400 hover:bg-neutral-800 hover:text-neutral-200"
              title="在新标签页中独立全屏预览"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* 沙箱 iframe 承载区 */}
      <div className="relative flex min-h-[320px] flex-1 items-center justify-center overflow-auto bg-neutral-950/70 p-4">
        {artifact ? (
          <div
            style={{
              width: getViewportWidth(viewportMode),
              maxWidth: '100%',
              height: '100%',
              minHeight: '320px',
              transition: 'width 0.25s ease-in-out',
            }}
            className="flex flex-col overflow-hidden rounded-lg border border-neutral-800 bg-neutral-900 shadow-xl"
          >
            <iframe
              key={`sandbox-frame-${sandboxReloadKey}`}
              title={artifact.title}
              srcDoc={iframeSrcDoc}
              sandbox="allow-scripts allow-same-origin"
              data-testid="sandbox-iframe"
              className="h-full w-full flex-1 border-0 bg-neutral-900"
            />
          </div>
        ) : (
          <div
            data-testid="sandbox-empty-state"
            className="flex flex-col items-center justify-center gap-2 text-center text-neutral-500"
          >
            <Maximize2 className="h-8 w-8 stroke-1 text-neutral-600" />
            <p className="text-xs">暂无待预览的应用或组件交付物</p>
            <p className="text-[11px] text-neutral-600">
              当智能体任务生成 HTML、React 或前端应用代码时将在此实时渲染
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
