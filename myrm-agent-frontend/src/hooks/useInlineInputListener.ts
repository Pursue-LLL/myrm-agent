'use client';

/**
 * [INPUT]
 * - Tauri event "inline-input-activated" from global shortcut handler
 * - useFlowPadStore (POS: FlowPad modal state - inline mode)
 *
 * [OUTPUT]
 * - Listens for Inline Input events and opens FlowPad in inline mode
 *
 * [POS]
 * Connects Tauri-side Inline Input shortcut to FlowPad Inline Mode.
 * Opens FlowPad with inline UI (local result display + Paste button).
 */

import { useEffect, useCallback } from 'react';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { useFlowPadStore } from '@/store/useFlowPadStore';

interface InlineInputPayload {
  screenshot: string;
  windowTitle: string;
  extractedText: string;
  selectedText?: string;
  sourcePid: number;
  timestamp: number;
}

export function useInlineInputListener() {
  const openInline = useFlowPadStore((s) => s.openInline);

  const handleActivated = useCallback(
    (payload: InlineInputPayload) => {
      openInline(
        {
          screenshot: payload.screenshot,
          windowTitle: payload.windowTitle,
          extractedText: payload.extractedText,
          selectedText: payload.selectedText || undefined,
          timestamp: payload.timestamp,
        },
        payload.sourcePid,
      );
    },
    [openInline],
  );

  useEffect(() => {
    if (!isTauriRuntime()) return;

    let disposed = false;
    let unlisten: (() => void) | undefined;

    const setup = async () => {
      try {
        const { listen } = await import('@tauri-apps/api/event');
        const listenerDispose = await listen<InlineInputPayload>('inline-input-activated', (event) => {
          handleActivated(event.payload);
        });
        if (disposed) {
          listenerDispose();
          return;
        }
        unlisten = listenerDispose;
      } catch (err) {
        console.error('Failed to setup inline input listener:', err);
      }
    };

    setup();

    return () => {
      disposed = true;
      unlisten?.();
      unlisten = undefined;
    };
  }, [handleActivated]);
}
