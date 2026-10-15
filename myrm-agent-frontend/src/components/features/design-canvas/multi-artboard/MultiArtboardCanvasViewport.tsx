'use client';

import React, { useRef, useState } from 'react';
import { Layers, Move, Link as LinkIcon } from 'lucide-react';
import { useMultiArtboardStore } from './useMultiArtboardStore';
import { Artboard, ArtboardLayer } from './multiArtboardTypes';
import { computeFlowLinkBezierPath } from './artboardLayoutEngine';

export const MultiArtboardCanvasViewport: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dragState, setDragState] = useState<{
    artboardId: string;
    startX: number;
    startY: number;
    initialX: number;
    initialY: number;
  } | null>(null);

  const [panState, setPanState] = useState<{
    startX: number;
    startY: number;
    initialPanX: number;
    initialPanY: number;
  } | null>(null);

  const {
    artboards,
    selectedArtboardId,
    selectedLayerId,
    flowLinks,
    showFlowLinks,
    viewport,
    selectArtboard,
    selectLayer,
    updateArtboardPosition,
    setViewportPan,
  } = useMultiArtboardStore();

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    // 鼠标中键或按住空格/Alt键为画布平移
    if (e.button === 1 || e.altKey || e.target === containerRef.current) {
      setPanState({
        startX: e.clientX,
        startY: e.clientY,
        initialPanX: viewport.panX,
        initialPanY: viewport.panY,
      });
      if (e.target === containerRef.current) {
        selectArtboard(null);
      }
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (panState) {
      const deltaX = e.clientX - panState.startX;
      const deltaY = e.clientY - panState.startY;
      setViewportPan(panState.initialPanX + deltaX, panState.initialPanY + deltaY);
      return;
    }

    if (dragState) {
      const deltaX = (e.clientX - dragState.startX) / viewport.zoom;
      const deltaY = (e.clientY - dragState.startY) / viewport.zoom;
      updateArtboardPosition(
        dragState.artboardId,
        Math.round(dragState.initialX + deltaX),
        Math.round(dragState.initialY + deltaY)
      );
    }
  };

  const handleMouseUp = () => {
    if (panState) {
      setPanState(null);
    }
    if (dragState) {
      setDragState(null);
    }
  };

  const handleArtboardHeaderMouseDown = (e: React.MouseEvent, artboard: Artboard) => {
    e.stopPropagation();
    selectArtboard(artboard.id);
    setDragState({
      artboardId: artboard.id,
      startX: e.clientX,
      startY: e.clientY,
      initialX: artboard.x,
      initialY: artboard.y,
    });
  };

  const renderLayer = (artboard: Artboard, layer: ArtboardLayer) => {
    const isLayerSelected =
      selectedArtboardId === artboard.id && selectedLayerId === layer.id;

    const baseStyle: React.CSSProperties = {
      position: 'absolute',
      left: `${layer.x}px`,
      top: `${layer.y}px`,
      width: `${layer.width}px`,
      height: `${layer.height}px`,
      opacity: layer.opacity,
      zIndex: layer.zIndex,
      outline: isLayerSelected ? '2px solid #38bdf8' : 'none',
      outlineOffset: '2px',
    };

    if (layer.type === 'button') {
      return (
        <button
          key={layer.id}
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            selectLayer(artboard.id, layer.id);
          }}
          style={{
            ...baseStyle,
            backgroundColor: layer.backgroundColor || '#6366f1',
            borderRadius: `${layer.borderRadius || 8}px`,
            color: layer.color || '#ffffff',
            fontSize: `${layer.fontSize || 14}px`,
            fontWeight: layer.fontWeight || 'normal',
            border: 'none',
            cursor: 'pointer',
          }}
          className="flex items-center justify-center font-medium shadow-md transition-transform hover:scale-[1.02] active:scale-[0.98]"
          title={layer.interactionTooltip || (layer.targetArtboardId ? `跳转至: ${layer.targetArtboardId}` : layer.name)}
        >
          <span>{layer.text || layer.name}</span>
          {layer.targetArtboardId && (
            <LinkIcon className="w-3.5 h-3.5 ml-1.5 opacity-80" aria-hidden="true" />
          )}
        </button>
      );
    }

    if (layer.type === 'text') {
      return (
        <div
          key={layer.id}
          onClick={(e) => {
            e.stopPropagation();
            selectLayer(artboard.id, layer.id);
          }}
          role="presentation"
          style={{
            ...baseStyle,
            fontSize: `${layer.fontSize || 14}px`,
            fontWeight: layer.fontWeight || 'normal',
            color: layer.color || '#f8fafc',
            fontFamily: layer.fontFamily,
          }}
          className="flex items-center select-none"
        >
          {layer.text}
        </div>
      );
    }

    if (layer.type === 'container') {
      return (
        <div
          key={layer.id}
          role="presentation"
          onClick={(e) => {
            e.stopPropagation();
            selectLayer(artboard.id, layer.id);
          }}
          style={{
            ...baseStyle,
            backgroundColor: layer.backgroundColor || '#0f172a',
            borderRadius: `${layer.borderRadius || 16}px`,
            border: layer.borderWidth ? `${layer.borderWidth}px solid ${layer.borderColor}` : 'none',
          }}
          className="shadow-2xl"
        />
      );
    }

    return null;
  };

  return (
    <div
      ref={containerRef}
      role="presentation"
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      className="relative w-full h-full overflow-hidden bg-slate-950 select-none cursor-grab active:cursor-grabbing outline-none"
      style={{
        backgroundImage:
          'radial-gradient(circle, rgba(148, 163, 184, 0.1) 1px, transparent 1px)',
        backgroundSize: `${24 * viewport.zoom}px ${24 * viewport.zoom}px`,
      }}
    >
      {/* 2D 缩放平移渲染世界 */}
      <div
        style={{
          transform: `translate(${viewport.panX}px, ${viewport.panY}px) scale(${viewport.zoom})`,
          transformOrigin: '0 0',
          position: 'absolute',
          left: 0,
          top: 0,
          width: '100%',
          height: '100%',
        }}
      >
        {/* SVG 跨画板交互流转连线 */}
        {showFlowLinks && (
          <svg
            className="absolute left-0 top-0 w-[4000px] h-[4000px] pointer-events-none z-10"
            style={{ overflow: 'visible' }}
          >
            <defs>
              <marker
                id="artboard-flow-arrow"
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 10 5 L 0 9 z" fill="#38bdf8" />
              </marker>
            </defs>
            {flowLinks.map((link) => {
              const srcArtboard = artboards.find((ab) => ab.id === link.sourceArtboardId);
              const tgtArtboard = artboards.find((ab) => ab.id === link.targetArtboardId);
              if (!srcArtboard || !tgtArtboard) {
                return null;
              }

              const srcLayer = srcArtboard.layers.find((l) => l.id === link.sourceLayerId);
              const { pathD, labelX, labelY } = computeFlowLinkBezierPath(
                srcArtboard,
                tgtArtboard,
                srcLayer
              );

              return (
                <g key={link.id} className="transition-all duration-300">
                  <path
                    d={pathD}
                    fill="none"
                    stroke="#38bdf8"
                    strokeWidth="2.5"
                    strokeDasharray="6 4"
                    markerEnd="url(#artboard-flow-arrow)"
                    className="opacity-80"
                  />
                  {link.label && (
                    <text
                      x={labelX}
                      y={labelY}
                      fill="#bae6fd"
                      fontSize="11"
                      textAnchor="middle"
                      className="font-medium bg-slate-900 px-1 select-none"
                    >
                      {link.label}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        )}

        {/* 渲染所有平铺画板 */}
        {artboards.map((artboard) => {
          const isSelected = selectedArtboardId === artboard.id;

          return (
            <div
              key={artboard.id}
              style={{
                position: 'absolute',
                left: `${artboard.x}px`,
                top: `${artboard.y}px`,
                width: `${artboard.width}px`,
                height: `${artboard.height}px`,
              }}
              className="group"
            >
              {/* 画板顶部标题栏 */}
              <div
                role="presentation"
                onMouseDown={(e) => { handleArtboardHeaderMouseDown(e, artboard); }}
                className={`flex items-center justify-between mb-2 px-3 py-1.5 rounded-lg text-xs font-semibold select-none cursor-move transition-colors ${
                  isSelected
                    ? 'bg-sky-500/20 text-sky-400 border border-sky-500/40'
                    : 'bg-slate-800/80 text-slate-300 border border-slate-700/60 hover:bg-slate-700/80'
                }`}
              >
                <div className="flex items-center space-x-1.5 truncate">
                  <Layers className="w-3.5 h-3.5 text-sky-400 shrink-0" aria-hidden="true" />
                  <span className="truncate">{artboard.title}</span>
                </div>
                <div className="flex items-center space-x-2 text-[10px] text-slate-400 shrink-0">
                  <span>{artboard.width}×{artboard.height}</span>
                  <Move className="w-3 h-3 opacity-60" aria-hidden="true" />
                </div>
              </div>

              {/* 画板实体内容容器 */}
              <div
                onClick={() => { selectArtboard(artboard.id); }}
                role="presentation"
                style={{
                  width: `${artboard.width}px`,
                  height: `${artboard.height}px`,
                }}
                className={`relative rounded-2xl overflow-hidden shadow-2xl transition-all ${
                  isSelected
                    ? 'ring-2 ring-sky-400 shadow-sky-950/40'
                    : 'ring-1 ring-slate-800 hover:ring-slate-700'
                }`}
              >
                {artboard.layers.map((layer) => renderLayer(artboard, layer))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
