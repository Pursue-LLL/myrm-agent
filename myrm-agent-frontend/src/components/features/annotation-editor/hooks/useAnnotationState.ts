/**
 * Annotation state management hook with undo/redo command stack.
 * Manages the list of annotation objects and provides history operations.
 */

import { useCallback, useRef, useState } from 'react';
import type { Annotation, AnnotationTool } from '../types';
import { DEFAULT_COLORS, DEFAULT_STROKE_WIDTH, DEFAULT_FONT_SIZE } from '../types';

const MAX_HISTORY = 50;

export function useAnnotationState() {
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [activeTool, setActiveTool] = useState<AnnotationTool>('arrow');
  const [activeColor, setActiveColor] = useState<string>(DEFAULT_COLORS[0]);
  const [strokeWidth, setStrokeWidth] = useState(DEFAULT_STROKE_WIDTH);
  const [fontSize, setFontSize] = useState(DEFAULT_FONT_SIZE);

  const undoStackRef = useRef<Annotation[][]>([]);
  const redoStackRef = useRef<Annotation[][]>([]);
  const [undoCount, setUndoCount] = useState(0);
  const [redoCount, setRedoCount] = useState(0);

  const pushToHistory = useCallback((prev: Annotation[]) => {
    undoStackRef.current = [...undoStackRef.current.slice(-MAX_HISTORY + 1), prev];
    redoStackRef.current = [];
    setUndoCount(undoStackRef.current.length);
    setRedoCount(0);
  }, []);

  const addAnnotation = useCallback(
    (annotation: Annotation) => {
      setAnnotations((prev) => {
        pushToHistory(prev);
        return [...prev, annotation];
      });
    },
    [pushToHistory],
  );

  const updateAnnotation = useCallback(
    (id: string, updater: (a: Annotation) => Annotation) => {
      setAnnotations((prev) => {
        pushToHistory(prev);
        return prev.map((a) => (a.id === id ? updater(a) : a));
      });
    },
    [pushToHistory],
  );

  const removeAnnotation = useCallback(
    (id: string) => {
      setAnnotations((prev) => {
        pushToHistory(prev);
        return prev.filter((a) => a.id !== id);
      });
    },
    [pushToHistory],
  );

  const undo = useCallback(() => {
    const stack = undoStackRef.current;
    if (stack.length === 0) return;
    const prev = stack[stack.length - 1];
    undoStackRef.current = stack.slice(0, -1);
    setAnnotations((current) => {
      redoStackRef.current = [...redoStackRef.current, current];
      setUndoCount(undoStackRef.current.length);
      setRedoCount(redoStackRef.current.length);
      return prev;
    });
  }, []);

  const redo = useCallback(() => {
    const stack = redoStackRef.current;
    if (stack.length === 0) return;
    const next = stack[stack.length - 1];
    redoStackRef.current = stack.slice(0, -1);
    setAnnotations((current) => {
      undoStackRef.current = [...undoStackRef.current, current];
      setUndoCount(undoStackRef.current.length);
      setRedoCount(redoStackRef.current.length);
      return next;
    });
  }, []);

  const clearAll = useCallback(() => {
    setAnnotations((prev) => {
      if (prev.length === 0) return prev;
      pushToHistory(prev);
      return [];
    });
  }, [pushToHistory]);

  const canUndo = undoCount > 0;
  const canRedo = redoCount > 0;

  return {
    annotations,
    activeTool,
    setActiveTool,
    activeColor,
    setActiveColor,
    strokeWidth,
    setStrokeWidth,
    fontSize,
    setFontSize,
    addAnnotation,
    updateAnnotation,
    removeAnnotation,
    undo,
    redo,
    clearAll,
    canUndo,
    canRedo,
  };
}
