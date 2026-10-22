'use client';

import React, { useRef, useState } from 'react';
import { useInfiniteCanvasStore } from './useInfiniteCanvasStore';
import { CanvasLayer, TextLayer } from './infiniteCanvasTypes';
import { screenToCanvasPoint } from './canvasLayerEngine';

export const InfiniteDesignCanvasViewport: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragState, setDragState] = useState<{
    layerId: string;
    startX: number;
    startY: number;
    initialLayerX: number;
    initialLayerY: number;
  } | null>(null);

  const [lassoDraft, setLassoDraft] = useState<{
    startX: number;
    startY: number;
    currentX: number;
    currentY: number;
  } | null>(null);

  const [editTextValue, setEditTextValue] = useState('');

  const {
    layers,
    selectedLayerId,
    editingTextLayerId,
    toolMode,
    viewport,
    selectLayer,
    updateLayerPosition,
    startInlineTextEdit,
    finishInlineTextEdit,
    cancelInlineTextEdit,
    setLassoBox,
  } = useInfiniteCanvasStore();

  React.useEffect(() => {
    if (editingTextLayerId && inputRef.current) {
      inputRef.current.focus();
    }
  }, [editingTextLayerId]);

  React.useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        cancelInlineTextEdit();
        selectLayer(null);
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => {
      window.removeEventListener('keydown', handleGlobalKeyDown);
    };
  }, [cancelInlineTextEdit, selectLayer]);

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!containerRef.current) {
      return;
    }

    const rect = containerRef.current.getBoundingClientRect();
    const canvasPt = screenToCanvasPoint(e.clientX, e.clientY, viewport, rect);

    // 框选模式 (Lasso Mode)
    if (toolMode === 'lasso' || e.altKey) {
      setLassoDraft({
        startX: canvasPt.x,
        startY: canvasPt.y,
        currentX: canvasPt.x,
        currentY: canvasPt.y,
      });
      return;
    }

    // 点击画布空白处取消选中
    if (e.target === containerRef.current) {
      selectLayer(null);
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!containerRef.current) {
      return;
    }
    const rect = containerRef.current.getBoundingClientRect();
    const canvasPt = screenToCanvasPoint(e.clientX, e.clientY, viewport, rect);

    if (lassoDraft) {
      setLassoDraft((prev) => (prev ? { ...prev, currentX: canvasPt.x, currentY: canvasPt.y } : null));
      return;
    }

    if (dragState) {
      const deltaX = canvasPt.x - dragState.startX;
      const deltaY = canvasPt.y - dragState.startY;
      updateLayerPosition(
        dragState.layerId,
        dragState.initialLayerX + deltaX,
        dragState.initialLayerY + deltaY
      );
    }
  };

  const handleMouseUp = () => {
    if (lassoDraft) {
      setLassoBox({
        startX: lassoDraft.startX,
        startY: lassoDraft.startY,
        endX: lassoDraft.currentX,
        endY: lassoDraft.currentY,
      });
      setLassoDraft(null);
    }
    if (dragState) {
      setDragState(null);
    }
  };

  const handleLayerMouseDown = (e: React.MouseEvent, layer: CanvasLayer) => {
    if (toolMode === 'lasso' || e.altKey || layer.isLocked) {
      return;
    }
    e.stopPropagation();
    selectLayer(layer.id);

    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      const canvasPt = screenToCanvasPoint(e.clientX, e.clientY, viewport, rect);
      setDragState({
        layerId: layer.id,
        startX: canvasPt.x,
        startY: canvasPt.y,
        initialLayerX: layer.x,
        initialLayerY: layer.y,
      });
    }
  };

  const handleTextDoubleClick = (e: React.MouseEvent, textLayer: TextLayer) => {
    e.stopPropagation();
    setEditTextValue(textLayer.text);
    startInlineTextEdit(textLayer.id);
  };

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      finishInlineTextEdit(editTextValue);
    } else if (e.key === 'Escape') {
      cancelInlineTextEdit();
    }
  };

  const renderLayer = (layer: CanvasLayer) => {
    const isSelected = selectedLayerId === layer.id;
    const isEditing = editingTextLayerId === layer.id;

    const baseStyle: React.CSSProperties = {
      position: 'absolute',
      left: `${layer.x}px`,
      top: `${layer.y}px`,
      width: `${layer.width}px`,
      height: `${layer.height}px`,
      opacity: layer.opacity,
      zIndex: layer.zIndex,
      cursor: isEditing ? 'text' : 'move',
      outline: isSelected ? '2px solid #38bdf8' : 'none',
      outlineOffset: '2px',
    };

    if (layer.type === 'container') {
      return (
        <button
          key={layer.id}
          type="button"
          aria-label={layer.name}
          onMouseDown={(e) => { handleLayerMouseDown(e, layer); }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              selectLayer(layer.id);
            }
          }}
          style={{
            ...baseStyle,
            backgroundColor: layer.backgroundColor,
            borderRadius: `${layer.borderRadius}px`,
            border: 'none',
            padding: 0,
            textAlign: 'left',
          }}
          className="shadow-2xl transition-shadow select-none block"
        />
      );
    }

    if (layer.type === 'shape') {
      return (
        <button
          key={layer.id}
          type="button"
          aria-label={layer.name}
          onMouseDown={(e) => { handleLayerMouseDown(e, layer); }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              selectLayer(layer.id);
            }
          }}
          style={{
            ...baseStyle,
            backgroundColor: layer.fillColor,
            borderRadius:
              layer.shapeType === 'circle'
                ? '50%'
                : layer.shapeType === 'pill'
                  ? `${(layer.borderRadius || 18)}px`
                  : '0px',
            border: 'none',
            padding: 0,
          }}
          className="select-none block"
        />
      );
    }

    if (layer.type === 'text') {
      if (isEditing) {
        return (
          <input
            key={layer.id}
            ref={inputRef}
            type="text"
            aria-label="编辑图层文本"
            value={editTextValue}
            onChange={(e) => { setEditTextValue(e.target.value); }}
            onBlur={() => { finishInlineTextEdit(editTextValue); }}
            onKeyDown={handleInputKeyDown}
            style={{
              ...baseStyle,
              fontSize: `${layer.fontSize}px`,
              fontWeight: layer.fontWeight,
              color: layer.color,
              fontFamily: layer.fontFamily,
              background: 'rgba(15, 23, 42, 0.85)',
              border: '1px solid #38bdf8',
              borderRadius: '4px',
              padding: '2px 6px',
            }}
          />
        );
      }

      return (
        <button
          key={layer.id}
          type="button"
          aria-label={layer.name}
          onMouseDown={(e) => { handleLayerMouseDown(e, layer); }}
          onDoubleClick={(e) => { handleTextDoubleClick(e, layer); }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              handleTextDoubleClick(e as unknown as React.MouseEvent, layer);
            }
          }}
          style={{
            ...baseStyle,
            fontSize: `${layer.fontSize}px`,
            fontWeight: layer.fontWeight,
            color: layer.color,
            fontFamily: layer.fontFamily,
            border: 'none',
            background: 'transparent',
            padding: 0,
            textAlign: 'left',
          }}
          className="flex items-center select-none"
          title="双击免 Token 直接修改文本"
        >
          {layer.text}
        </button>
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
      className="relative w-full h-full overflow-hidden bg-slate-950 select-none cursor-crosshair"
      style={{
        backgroundImage:
          'radial-gradient(circle, rgba(148, 163, 184, 0.12) 1px, transparent 1px)',
        backgroundSize: `${20 * viewport.zoom}px ${20 * viewport.zoom}px`,
      }}
    >
      {/* Transformed Canvas World */}
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
        {layers.map((layer) => renderLayer(layer))}

        {/* Live Lasso Selection Box Preview */}
        {lassoDraft && (
          <div
            style={{
              position: 'absolute',
              left: `${Math.min(lassoDraft.startX, lassoDraft.currentX)}px`,
              top: `${Math.min(lassoDraft.startY, lassoDraft.currentY)}px`,
              width: `${Math.abs(lassoDraft.currentX - lassoDraft.startX)}px`,
              height: `${Math.abs(lassoDraft.currentY - lassoDraft.startY)}px`,
              border: '2px dashed #f59e0b',
              backgroundColor: 'rgba(245, 158, 11, 0.15)',
              pointerEvents: 'none',
              zIndex: 9999,
            }}
          />
        )}
      </div>
    </div>
  );
};
