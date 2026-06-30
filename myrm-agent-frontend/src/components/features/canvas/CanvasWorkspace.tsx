/**
 * [INPUT]
 * - tldraw (POS: Infinite canvas library)
 * - @/services/canvas (POS: Canvas API)
 *
 * [OUTPUT]
 * - CanvasWorkspace: React component — tldraw-based infinite canvas editor
 *
 * [POS]
 * Core infinite canvas workspace component. Wraps tldraw with persistence
 * (debounced auto-save to backend), selection sync, and SSE-based real-time
 * notifications for Agent ↔ frontend interop.
 */

'use client';

import { useCallback, useEffect, useRef } from 'react';
import {
  type Editor,
  type TLStoreSnapshot,
  Tldraw,
} from 'tldraw';
import 'tldraw/tldraw.css';

import {
  createCanvasEventSource,
  loadSnapshot,
  saveSelection,
  saveSnapshot,
} from '@/services/canvas';

const SAVE_DEBOUNCE_MS = 1500;
const SSE_RECONNECT_MS = 3000;

interface CanvasWorkspaceProps {
  canvasId: string;
  className?: string;
}

export default function CanvasWorkspace({ canvasId, className }: CanvasWorkspaceProps) {
  const editorRef = useRef<Editor | null>(null);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMountedRef = useRef(true);
  const cleanupRef = useRef<(() => void) | null>(null);

  const debouncedSave = useCallback(
    (editor: Editor) => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => {
        if (!isMountedRef.current) return;
        const snapshot = editor.store.getStoreSnapshot();
        saveSnapshot(canvasId, snapshot as unknown as Record<string, unknown>).catch((err) =>
          console.error('[canvas] save failed:', err),
        );
      }, SAVE_DEBOUNCE_MS);
    },
    [canvasId],
  );

  const handleSelectionChange = useCallback(
    (editor: Editor) => {
      const selectedShapes = editor.getSelectedShapes();
      if (selectedShapes.length > 0) {
        const simplified = selectedShapes.map((s) => ({
          id: s.id,
          type: s.type,
          x: s.x,
          y: s.y,
          props: s.props,
        }));
        saveSelection(canvasId, simplified).catch((err) =>
          console.error('[canvas] selection sync failed:', err),
        );
      }
    },
    [canvasId],
  );

  const handleMount = useCallback(
    (editor: Editor) => {
      editorRef.current = editor;

      loadSnapshot(canvasId)
        .then((snapshot) => {
          if (snapshot && isMountedRef.current) {
            editor.store.loadStoreSnapshot(snapshot as unknown as TLStoreSnapshot);
          }
        })
        .catch((err) => console.error('[canvas] load snapshot failed:', err));

      const removeStoreListener = editor.store.listen(
        () => debouncedSave(editor),
        { source: 'user', scope: 'document' },
      );

      const removeSelectionListener = editor.store.listen(
        () => handleSelectionChange(editor),
        { source: 'user', scope: 'session' },
      );

      let eventSource: EventSource | null = null;
      let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

      function connectSSE() {
        eventSource = createCanvasEventSource(canvasId);
        eventSource.addEventListener('canvas-changed', () => {
          loadSnapshot(canvasId)
            .then((freshSnapshot) => {
              if (freshSnapshot && isMountedRef.current) {
                editor.store.loadStoreSnapshot(freshSnapshot as unknown as TLStoreSnapshot);
              }
            })
            .catch(() => {});
        });
        eventSource.onerror = () => {
          eventSource?.close();
          eventSource = null;
          if (isMountedRef.current) {
            reconnectTimer = setTimeout(connectSSE, SSE_RECONNECT_MS);
          }
        };
      }
      connectSSE();

      const cleanup = () => {
        removeStoreListener();
        removeSelectionListener();
        eventSource?.close();
        eventSource = null;
        if (reconnectTimer) clearTimeout(reconnectTimer);
      };

      cleanupRef.current = cleanup;
      return cleanup;
    },
    [canvasId, debouncedSave, handleSelectionChange],
  );

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      cleanupRef.current?.();
    };
  }, []);

  return (
    <div className={`w-full h-full ${className ?? ''}`}>
      <Tldraw onMount={handleMount} />
    </div>
  );
}
