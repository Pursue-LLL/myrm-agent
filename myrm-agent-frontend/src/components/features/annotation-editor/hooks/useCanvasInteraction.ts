/**
 * Canvas interaction hook using Pointer Events for unified mouse/touch/pen input.
 * Handles drawing new annotations based on the active tool.
 */

import { useCallback, useRef, useState } from 'react';
import type { Annotation, AnnotationTool, Point, FreehandAnnotation } from '../types';

interface UseCanvasInteractionParams {
  activeTool: AnnotationTool;
  activeColor: string;
  strokeWidth: number;
  fontSize: number;
  addAnnotation: (annotation: Annotation) => void;
  canvasScale: number;
}

function generateId(): string {
  return `ann_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function getCanvasPoint(e: React.PointerEvent, canvas: HTMLCanvasElement, scale: number): Point {
  const rect = canvas.getBoundingClientRect();
  return {
    x: (e.clientX - rect.left) / scale,
    y: (e.clientY - rect.top) / scale,
  };
}

export function useCanvasInteraction({
  activeTool,
  activeColor,
  strokeWidth,
  fontSize,
  addAnnotation,
  canvasScale,
}: UseCanvasInteractionParams) {
  const [isDrawing, setIsDrawing] = useState(false);
  const [currentDraw, setCurrentDraw] = useState<Annotation | null>(null);
  const startPointRef = useRef<Point>({ x: 0, y: 0 });
  const freehandPointsRef = useRef<Point[]>([]);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      if (activeTool === 'text') return;

      const canvas = e.currentTarget;
      canvas.setPointerCapture(e.pointerId);
      const point = getCanvasPoint(e, canvas, canvasScale);
      startPointRef.current = point;
      setIsDrawing(true);

      if (activeTool === 'freehand') {
        freehandPointsRef.current = [point];
        setCurrentDraw({
          id: generateId(),
          tool: 'freehand',
          color: activeColor,
          strokeWidth,
          points: [point],
        });
      }
    },
    [activeTool, activeColor, strokeWidth, canvasScale],
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      if (!isDrawing) return;

      const canvas = e.currentTarget;
      const point = getCanvasPoint(e, canvas, canvasScale);
      const start = startPointRef.current;

      if (activeTool === 'freehand') {
        freehandPointsRef.current.push(point);
        setCurrentDraw((prev) => {
          if (!prev || prev.tool !== 'freehand') return prev;
          return { ...prev, points: [...freehandPointsRef.current] };
        });
        return;
      }

      const base = { id: '__preview__', color: activeColor, strokeWidth };

      switch (activeTool) {
        case 'arrow':
          setCurrentDraw({ ...base, tool: 'arrow', start, end: point });
          break;
        case 'rectangle':
          setCurrentDraw({ ...base, tool: 'rectangle', start, end: point, filled: false });
          break;
        case 'ellipse':
          setCurrentDraw({
            ...base,
            tool: 'ellipse',
            center: { x: (start.x + point.x) / 2, y: (start.y + point.y) / 2 },
            radiusX: Math.abs(point.x - start.x) / 2,
            radiusY: Math.abs(point.y - start.y) / 2,
            filled: false,
          });
          break;
        case 'highlight':
          setCurrentDraw({ ...base, tool: 'highlight', start, end: point, opacity: 0.35 });
          break;
        case 'blur':
          setCurrentDraw({ ...base, tool: 'blur', start, end: point, intensity: 8 });
          break;
        case 'crop':
          setCurrentDraw({ ...base, tool: 'crop', start, end: point });
          break;
      }
    },
    [isDrawing, activeTool, activeColor, strokeWidth, canvasScale],
  );

  const handlePointerUp = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      if (!isDrawing) return;

      const canvas = e.currentTarget;
      canvas.releasePointerCapture(e.pointerId);
      setIsDrawing(false);

      const point = getCanvasPoint(e, canvas, canvasScale);
      const start = startPointRef.current;
      const id = generateId();
      const base = { id, color: activeColor, strokeWidth };

      const dx = Math.abs(point.x - start.x);
      const dy = Math.abs(point.y - start.y);
      const minDistance = 5;

      if (activeTool === 'freehand') {
        const points = freehandPointsRef.current;
        if (points.length > 2) {
          addAnnotation({ ...base, tool: 'freehand', points } as FreehandAnnotation);
        }
      } else if (dx > minDistance || dy > minDistance) {
        switch (activeTool) {
          case 'arrow':
            addAnnotation({ ...base, tool: 'arrow', start, end: point });
            break;
          case 'rectangle':
            addAnnotation({ ...base, tool: 'rectangle', start, end: point, filled: false });
            break;
          case 'ellipse':
            addAnnotation({
              ...base,
              tool: 'ellipse',
              center: { x: (start.x + point.x) / 2, y: (start.y + point.y) / 2 },
              radiusX: dx / 2,
              radiusY: dy / 2,
              filled: false,
            });
            break;
          case 'highlight':
            addAnnotation({ ...base, tool: 'highlight', start, end: point, opacity: 0.35 });
            break;
          case 'blur':
            addAnnotation({ ...base, tool: 'blur', start, end: point, intensity: 8 });
            break;
          case 'crop':
            addAnnotation({ ...base, tool: 'crop', start, end: point });
            break;
        }
      }

      setCurrentDraw(null);
      freehandPointsRef.current = [];
    },
    [isDrawing, activeTool, activeColor, strokeWidth, canvasScale, addAnnotation],
  );

  const [textInputState, setTextInputState] = useState<{
    visible: boolean;
    position: Point;
    screenPosition: Point;
  }>({ visible: false, position: { x: 0, y: 0 }, screenPosition: { x: 0, y: 0 } });

  const handleCanvasClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (activeTool !== 'text') return;

      const canvas = e.currentTarget;
      const rect = canvas.getBoundingClientRect();
      const point: Point = {
        x: (e.clientX - rect.left) / canvasScale,
        y: (e.clientY - rect.top) / canvasScale,
      };

      setTextInputState({
        visible: true,
        position: point,
        screenPosition: { x: e.clientX - rect.left, y: e.clientY - rect.top },
      });
    },
    [activeTool, canvasScale],
  );

  const commitTextInput = useCallback(
    (content: string) => {
      if (content.trim()) {
        addAnnotation({
          id: generateId(),
          tool: 'text',
          color: activeColor,
          strokeWidth,
          position: textInputState.position,
          content: content.trim(),
          fontSize,
        });
      }
      setTextInputState((s) => ({ ...s, visible: false }));
    },
    [activeColor, strokeWidth, fontSize, textInputState.position, addAnnotation],
  );

  const cancelTextInput = useCallback(() => {
    setTextInputState((s) => ({ ...s, visible: false }));
  }, []);

  return {
    isDrawing,
    currentDraw,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handleCanvasClick,
    textInputState,
    commitTextInput,
    cancelTextInput,
  };
}
