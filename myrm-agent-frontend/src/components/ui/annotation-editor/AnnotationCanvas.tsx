/**
 * Dual-layer Canvas renderer for the annotation editor.
 * Bottom layer: original image (static). Top layer: annotation drawings (interactive).
 */

'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import type { Annotation, AnnotationTool, Point } from './types';
import { MAX_OUTPUT_WIDTH } from './types';
import { useCanvasInteraction } from './hooks/useCanvasInteraction';

interface AnnotationCanvasProps {
  imageSrc: string;
  annotations: Annotation[];
  activeTool: AnnotationTool;
  activeColor: string;
  strokeWidth: number;
  fontSize: number;
  addAnnotation: (annotation: Annotation) => void;
}

function drawArrow(ctx: CanvasRenderingContext2D, start: Point, end: Point, color: string, width: number) {
  const headLen = Math.max(width * 4, 12);
  const angle = Math.atan2(end.y - start.y, end.x - start.x);

  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  ctx.beginPath();
  ctx.moveTo(start.x, start.y);
  ctx.lineTo(end.x, end.y);
  ctx.stroke();

  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(end.x, end.y);
  ctx.lineTo(end.x - headLen * Math.cos(angle - Math.PI / 6), end.y - headLen * Math.sin(angle - Math.PI / 6));
  ctx.lineTo(end.x - headLen * Math.cos(angle + Math.PI / 6), end.y - headLen * Math.sin(angle + Math.PI / 6));
  ctx.closePath();
  ctx.fill();
}

function drawAnnotation(ctx: CanvasRenderingContext2D, ann: Annotation, blurCanvas?: HTMLCanvasElement) {
  ctx.strokeStyle = ann.color;
  ctx.lineWidth = ann.strokeWidth;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  switch (ann.tool) {
    case 'arrow':
      drawArrow(ctx, ann.start, ann.end, ann.color, ann.strokeWidth);
      break;

    case 'rectangle':
      ctx.beginPath();
      ctx.rect(ann.start.x, ann.start.y, ann.end.x - ann.start.x, ann.end.y - ann.start.y);
      ctx.stroke();
      break;

    case 'ellipse':
      ctx.beginPath();
      ctx.ellipse(ann.center.x, ann.center.y, ann.radiusX, ann.radiusY, 0, 0, Math.PI * 2);
      ctx.stroke();
      break;

    case 'text':
      ctx.fillStyle = ann.color;
      ctx.font = `bold ${ann.fontSize}px sans-serif`;
      ctx.textBaseline = 'top';
      ctx.fillText(ann.content, ann.position.x, ann.position.y);
      break;

    case 'freehand':
      if (ann.points.length < 2) break;
      ctx.beginPath();
      ctx.moveTo(ann.points[0].x, ann.points[0].y);
      for (let i = 1; i < ann.points.length; i++) {
        ctx.lineTo(ann.points[i].x, ann.points[i].y);
      }
      ctx.stroke();
      break;

    case 'highlight': {
      ctx.save();
      ctx.globalAlpha = ann.opacity;
      ctx.fillStyle = ann.color;
      const hx = Math.min(ann.start.x, ann.end.x);
      const hy = Math.min(ann.start.y, ann.end.y);
      const hw = Math.abs(ann.end.x - ann.start.x);
      const hh = Math.abs(ann.end.y - ann.start.y);
      ctx.fillRect(hx, hy, hw, hh);
      ctx.restore();
      break;
    }

    case 'blur': {
      if (!blurCanvas) break;
      const bx = Math.min(ann.start.x, ann.end.x);
      const by = Math.min(ann.start.y, ann.end.y);
      const bw = Math.abs(ann.end.x - ann.start.x);
      const bh = Math.abs(ann.end.y - ann.start.y);
      if (bw < 1 || bh < 1) break;

      const tempCanvas = document.createElement('canvas');
      tempCanvas.width = bw;
      tempCanvas.height = bh;
      const tempCtx = tempCanvas.getContext('2d');
      if (!tempCtx) break;
      tempCtx.filter = `blur(${ann.intensity}px)`;
      tempCtx.drawImage(blurCanvas, bx, by, bw, bh, 0, 0, bw, bh);
      ctx.drawImage(tempCanvas, bx, by);
      break;
    }

    case 'crop': {
      ctx.save();
      ctx.setLineDash([6, 4]);
      ctx.strokeStyle = '#3b82f6';
      ctx.lineWidth = 2;
      const cx = Math.min(ann.start.x, ann.end.x);
      const cy = Math.min(ann.start.y, ann.end.y);
      const cw = Math.abs(ann.end.x - ann.start.x);
      const ch = Math.abs(ann.end.y - ann.start.y);
      ctx.strokeRect(cx, cy, cw, ch);

      ctx.fillStyle = 'rgba(0,0,0,0.4)';
      ctx.fillRect(0, 0, ctx.canvas.width, cy);
      ctx.fillRect(0, cy, cx, ch);
      ctx.fillRect(cx + cw, cy, ctx.canvas.width - cx - cw, ch);
      ctx.fillRect(0, cy + ch, ctx.canvas.width, ctx.canvas.height - cy - ch);
      ctx.restore();
      break;
    }
  }
}

export function AnnotationCanvas({
  imageSrc,
  annotations,
  activeTool,
  activeColor,
  strokeWidth,
  fontSize,
  addAnnotation,
}: AnnotationCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bgCanvasRef = useRef<HTMLCanvasElement>(null);
  const drawCanvasRef = useRef<HTMLCanvasElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const [canvasSize, setCanvasSize] = useState({ width: 800, height: 600 });
  const [scale, setScale] = useState(1);
  const [textValue, setTextValue] = useState('');
  const textInputRef = useRef<HTMLInputElement>(null);

  const resizeToContainer = useCallback(() => {
    const img = imageRef.current;
    const container = containerRef.current;
    if (!img || !container) return;

    const containerWidth = container.clientWidth;
    const containerHeight = container.clientHeight;
    const imgAspect = img.naturalWidth / img.naturalHeight;
    const containerAspect = containerWidth / containerHeight;

    let displayWidth: number;
    let displayHeight: number;

    if (imgAspect > containerAspect) {
      displayWidth = containerWidth;
      displayHeight = containerWidth / imgAspect;
    } else {
      displayHeight = containerHeight;
      displayWidth = containerHeight * imgAspect;
    }

    const scaleRatio = displayWidth / img.naturalWidth;
    setScale(scaleRatio);
    setCanvasSize({ width: displayWidth, height: displayHeight });

    const bgCanvas = bgCanvasRef.current;
    if (bgCanvas) {
      bgCanvas.width = img.naturalWidth;
      bgCanvas.height = img.naturalHeight;
      const bgCtx = bgCanvas.getContext('2d');
      if (bgCtx) bgCtx.drawImage(img, 0, 0);
    }

    const drawCanvas = drawCanvasRef.current;
    if (drawCanvas) {
      drawCanvas.width = img.naturalWidth;
      drawCanvas.height = img.naturalHeight;
    }
  }, []);

  const loadImage = useCallback(() => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      imageRef.current = img;
      resizeToContainer();
    };
    img.src = imageSrc;
  }, [imageSrc, resizeToContainer]);

  useEffect(() => {
    loadImage();
  }, [loadImage]);

  useEffect(() => {
    const handleResize = () => {
      if (imageRef.current) resizeToContainer();
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [resizeToContainer]);

  const {
    currentDraw,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handleCanvasClick,
    textInputState,
    commitTextInput,
    cancelTextInput,
  } = useCanvasInteraction({
    activeTool,
    activeColor,
    strokeWidth,
    fontSize,
    addAnnotation,
    canvasScale: scale,
  });

  useEffect(() => {
    const canvas = drawCanvasRef.current;
    if (!canvas || !imageRef.current) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const ann of annotations) {
      drawAnnotation(ctx, ann, bgCanvasRef.current ?? undefined);
    }
    if (currentDraw) {
      drawAnnotation(ctx, currentDraw, bgCanvasRef.current ?? undefined);
    }
  }, [annotations, currentDraw]);

  useEffect(() => {
    if (textInputState.visible && textInputRef.current) {
      setTextValue('');
      setTimeout(() => textInputRef.current?.focus(), 50);
    }
  }, [textInputState.visible]);

  const handleTextKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      commitTextInput(textValue);
      setTextValue('');
    } else if (e.key === 'Escape') {
      cancelTextInput();
      setTextValue('');
    }
  };

  const exportImage = useCallback((): { dataUrl: string; textAnnotations: string[] } | null => {
    const img = imageRef.current;
    if (!img) return null;

    let outputWidth = img.naturalWidth;
    let outputHeight = img.naturalHeight;
    let cropX = 0;
    let cropY = 0;
    let cropW = img.naturalWidth;
    let cropH = img.naturalHeight;

    const cropAnnotation = annotations.find((a) => a.tool === 'crop');
    if (cropAnnotation && cropAnnotation.tool === 'crop') {
      cropX = Math.min(cropAnnotation.start.x, cropAnnotation.end.x);
      cropY = Math.min(cropAnnotation.start.y, cropAnnotation.end.y);
      cropW = Math.abs(cropAnnotation.end.x - cropAnnotation.start.x);
      cropH = Math.abs(cropAnnotation.end.y - cropAnnotation.start.y);
      outputWidth = cropW;
      outputHeight = cropH;
    }

    if (outputWidth > MAX_OUTPUT_WIDTH) {
      const ratio = MAX_OUTPUT_WIDTH / outputWidth;
      outputHeight = Math.round(outputHeight * ratio);
      outputWidth = MAX_OUTPUT_WIDTH;
    }

    const exportCanvas = document.createElement('canvas');
    exportCanvas.width = outputWidth;
    exportCanvas.height = outputHeight;
    const ctx = exportCanvas.getContext('2d');
    if (!ctx) return null;

    ctx.drawImage(img, cropX, cropY, cropW, cropH, 0, 0, outputWidth, outputHeight);

    const scaleX = outputWidth / cropW;
    const scaleY = outputHeight / cropH;
    const nonCropAnnotations = annotations.filter((a) => a.tool !== 'crop');

    for (const ann of nonCropAnnotations) {
      ctx.save();
      ctx.translate(-cropX * scaleX, -cropY * scaleY);
      ctx.scale(scaleX, scaleY);
      drawAnnotation(ctx, ann, bgCanvasRef.current ?? undefined);
      ctx.restore();
    }

    const textAnnotations = annotations
      .filter((a): a is Extract<Annotation, { tool: 'text' }> => a.tool === 'text')
      .map((a) => a.content);

    return { dataUrl: exportCanvas.toDataURL('image/png'), textAnnotations };
  }, [annotations]);

  useEffect(() => {
    (window as unknown as Record<string, unknown>).__annotationExport = exportImage;
    return () => {
      delete (window as unknown as Record<string, unknown>).__annotationExport;
    };
  }, [exportImage]);

  return (
    <div ref={containerRef} className="relative flex-1 flex items-center justify-center overflow-hidden bg-black/20">
      <div className="relative" style={{ width: canvasSize.width, height: canvasSize.height }}>
        <canvas
          ref={bgCanvasRef}
          className="absolute inset-0 w-full h-full pointer-events-none"
          style={{ imageRendering: 'auto' }}
        />
        <canvas
          ref={drawCanvasRef}
          className="absolute inset-0 w-full h-full touch-none"
          style={{ cursor: activeTool === 'text' ? 'text' : 'crosshair' }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onClick={handleCanvasClick}
        />
        {textInputState.visible && (
          <input
            ref={textInputRef}
            type="text"
            value={textValue}
            onChange={(e) => setTextValue(e.target.value)}
            onKeyDown={handleTextKeyDown}
            onBlur={() => {
              commitTextInput(textValue);
              setTextValue('');
            }}
            className="absolute z-50 bg-transparent border-b-2 border-current outline-none font-bold px-1"
            style={{
              left: textInputState.screenPosition.x,
              top: textInputState.screenPosition.y,
              color: activeColor,
              fontSize: `${fontSize * scale}px`,
              minWidth: '100px',
            }}
            placeholder="..."
          />
        )}
      </div>
    </div>
  );
}
