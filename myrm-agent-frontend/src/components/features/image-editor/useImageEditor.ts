import { useState, useRef, useCallback, useEffect } from 'react';
import type { ToolType, DrawOperation, Point } from './tools/types';
import { PALETTE_COLORS, LINE_WIDTHS, MAX_UNDO_STEPS, MAX_IMAGE_DIMENSION } from './tools/types';
import { renderAllOperations, renderOperation } from './tools/drawingEngine';

export interface UseImageEditorReturn {
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  tool: ToolType;
  setTool: (t: ToolType) => void;
  color: string;
  setColor: (c: string) => void;
  lineWidth: number;
  setLineWidth: (w: number) => void;
  rotation: number;
  rotate90: () => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  loadImage: (src: string) => Promise<void>;
  exportAsBlob: () => Promise<Blob | null>;
  handlePointerDown: (e: React.PointerEvent) => void;
  handlePointerMove: (e: React.PointerEvent) => void;
  handlePointerUp: () => void;
  handleTextSubmit: (text: string) => void;
  pendingTextPosition: Point | null;
  isDrawing: boolean;
}

export function useImageEditor(): UseImageEditorReturn {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const baseImageRef = useRef<HTMLImageElement | null>(null);

  const [tool, setTool] = useState<ToolType>('freehand');
  const [color, setColor] = useState<string>(PALETTE_COLORS[0]);
  const [lineWidth, setLineWidth] = useState<number>(LINE_WIDTHS[1]);
  const [rotation, setRotation] = useState(0);

  const [operations, setOperations] = useState<DrawOperation[]>([]);
  const [redoStack, setRedoStack] = useState<DrawOperation[]>([]);

  const currentOpRef = useRef<DrawOperation | null>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [pendingTextPosition, setPendingTextPosition] = useState<Point | null>(null);

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    const baseImage = baseImageRef.current;
    if (!canvas || !baseImage) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    renderAllOperations(ctx, baseImage, operations);
  }, [operations]);

  const loadImage = useCallback(async (src: string): Promise<void> => {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => {
        let { width, height } = img;
        if (width > MAX_IMAGE_DIMENSION || height > MAX_IMAGE_DIMENSION) {
          const scale = MAX_IMAGE_DIMENSION / Math.max(width, height);
          width = Math.round(width * scale);
          height = Math.round(height * scale);
        }

        const canvas = canvasRef.current;
        if (!canvas) { reject(new Error('Canvas not ready')); return; }
        canvas.width = width;
        canvas.height = height;
        baseImageRef.current = img;
        setOperations([]);
        setRedoStack([]);
        setRotation(0);

        const ctx = canvas.getContext('2d');
        if (ctx) ctx.drawImage(img, 0, 0, width, height);
        resolve();
      };
      img.onerror = () => reject(new Error('Failed to load image'));
      img.src = src;
    });
  }, []);

  const pushOperation = useCallback((op: DrawOperation) => {
    setOperations((prev) => {
      const next = [...prev, op];
      return next.length > MAX_UNDO_STEPS ? next.slice(next.length - MAX_UNDO_STEPS) : next;
    });
    setRedoStack([]);
  }, []);

  const undo = useCallback(() => {
    setOperations((prev) => {
      if (prev.length === 0) return prev;
      const last = prev[prev.length - 1];
      setRedoStack((r) => [...r, last]);
      return prev.slice(0, -1);
    });
  }, []);

  const redo = useCallback(() => {
    setRedoStack((prev) => {
      if (prev.length === 0) return prev;
      const last = prev[prev.length - 1];
      setOperations((ops) => [...ops, last]);
      return prev.slice(0, -1);
    });
  }, []);

  const rotate90 = useCallback(() => {
    const canvas = canvasRef.current;
    const baseImage = baseImageRef.current;
    if (!canvas || !baseImage) return;

    const tempCanvas = document.createElement('canvas');
    tempCanvas.width = canvas.height;
    tempCanvas.height = canvas.width;
    const tCtx = tempCanvas.getContext('2d');
    if (!tCtx) return;

    tCtx.translate(tempCanvas.width / 2, tempCanvas.height / 2);
    tCtx.rotate(Math.PI / 2);
    tCtx.drawImage(canvas, -canvas.width / 2, -canvas.height / 2);

    tempCanvas.toBlob((blob) => {
      if (!blob) return;
      const blobUrl = URL.createObjectURL(blob);
      const rotatedImg = new Image();
      rotatedImg.onload = () => {
        canvas.width = tempCanvas.width;
        canvas.height = tempCanvas.height;
        baseImageRef.current = rotatedImg;
        setOperations([]);
        setRedoStack([]);
        setRotation((r) => (r + 90) % 360);
        const ctx = canvas.getContext('2d');
        if (ctx) ctx.drawImage(rotatedImg, 0, 0);
        URL.revokeObjectURL(blobUrl);
      };
      rotatedImg.src = blobUrl;
    });
  }, []);

  const getCanvasPoint = useCallback((e: React.PointerEvent): Point | null => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    };
  }, []);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    const pt = getCanvasPoint(e);
    if (!pt) return;

    if (tool === 'text') {
      setPendingTextPosition(pt);
      return;
    }

    setIsDrawing(true);
    currentOpRef.current = { tool, color, lineWidth, points: [pt] };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }, [tool, color, lineWidth, getCanvasPoint]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!isDrawing || !currentOpRef.current) return;
    const pt = getCanvasPoint(e);
    if (!pt) return;

    currentOpRef.current.points.push(pt);

    const canvas = canvasRef.current;
    const baseImage = baseImageRef.current;
    if (!canvas || !baseImage) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    renderAllOperations(ctx, baseImage, operations);
    renderOperation(ctx, currentOpRef.current);
  }, [isDrawing, getCanvasPoint, operations]);

  const handlePointerUp = useCallback(() => {
    if (!isDrawing || !currentOpRef.current) return;
    setIsDrawing(false);

    if (currentOpRef.current.points.length >= 2) {
      pushOperation(currentOpRef.current);
    }
    currentOpRef.current = null;
  }, [isDrawing, pushOperation]);

  const handleTextSubmit = useCallback((text: string) => {
    if (!pendingTextPosition || !text.trim()) {
      setPendingTextPosition(null);
      return;
    }
    pushOperation({
      tool: 'text',
      color,
      lineWidth,
      points: [pendingTextPosition],
      text: text.trim(),
      fontSize: 20,
    });
    setPendingTextPosition(null);
  }, [pendingTextPosition, color, lineWidth, pushOperation]);

  const exportAsBlob = useCallback(async (): Promise<Blob | null> => {
    const canvas = canvasRef.current;
    const baseImage = baseImageRef.current;
    if (!canvas || !baseImage) return null;

    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    renderAllOperations(ctx, baseImage, operations);

    return new Promise((resolve) => {
      canvas.toBlob((blob) => resolve(blob), 'image/png');
    });
  }, [operations]);

  useEffect(() => {
    redraw();
  }, [redraw]);

  return {
    canvasRef,
    tool,
    setTool,
    color,
    setColor,
    lineWidth,
    setLineWidth,
    rotation,
    rotate90,
    undo,
    redo,
    canUndo: operations.length > 0,
    canRedo: redoStack.length > 0,
    loadImage,
    exportAsBlob,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handleTextSubmit,
    pendingTextPosition,
    isDrawing,
  };
}
