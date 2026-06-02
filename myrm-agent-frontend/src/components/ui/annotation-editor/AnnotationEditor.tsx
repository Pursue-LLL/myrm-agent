/**
 * Main Annotation Editor component.
 * Full-screen modal that allows users to annotate images before sending to AI.
 */

'use client';

import { useCallback, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AnnotationCanvas } from './AnnotationCanvas';
import { AnnotationToolbar } from './AnnotationToolbar';
import { useAnnotationState } from './hooks/useAnnotationState';

interface AnnotationEditorProps {
  imageSrc: string;
  onSave: (result: { dataUrl: string; textAnnotations: string[] }) => void;
  onClose: () => void;
}

export default function AnnotationEditor({ imageSrc, onSave, onClose }: AnnotationEditorProps) {
  const {
    annotations,
    activeTool,
    setActiveTool,
    activeColor,
    setActiveColor,
    strokeWidth,
    setStrokeWidth,
    fontSize,
    addAnnotation,
    undo,
    redo,
    clearAll,
    canUndo,
    canRedo,
  } = useAnnotationState();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      const isMod = e.metaKey || e.ctrlKey;
      if (isMod && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        undo();
      } else if (isMod && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
        e.preventDefault();
        redo();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose, undo, redo]);

  const handleSave = useCallback(() => {
    const exportFn = (window as unknown as Record<string, unknown>).__annotationExport as
      | (() => { dataUrl: string; textAnnotations: string[] } | null)
      | undefined;
    if (!exportFn) return;
    const result = exportFn();
    if (result) {
      onSave(result);
    }
  }, [onSave]);

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
        className="fixed inset-0 z-[9999] flex flex-col bg-background"
      >
        <AnnotationToolbar
          activeTool={activeTool}
          setActiveTool={setActiveTool}
          activeColor={activeColor}
          setActiveColor={setActiveColor}
          strokeWidth={strokeWidth}
          setStrokeWidth={setStrokeWidth}
          onUndo={undo}
          onRedo={redo}
          onClear={clearAll}
          onSave={handleSave}
          onClose={onClose}
          canUndo={canUndo}
          canRedo={canRedo}
        />

        <AnnotationCanvas
          imageSrc={imageSrc}
          annotations={annotations}
          activeTool={activeTool}
          activeColor={activeColor}
          strokeWidth={strokeWidth}
          fontSize={fontSize}
          addAnnotation={addAnnotation}
        />
      </motion.div>
    </AnimatePresence>
  );
}
