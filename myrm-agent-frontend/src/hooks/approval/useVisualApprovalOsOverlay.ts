'use client';

/**
 * [INPUT]
 * - @/lib/approval/resolveDesktopOverlayTarget (POS: shared overlay target selection)
 * - @/lib/approval/visualApprovalOsOverlay (POS: Tauri overlay IPC bridge)
 * - pending inline desktop visual approval requests + inspector snapshots
 *
 * [OUTPUT]
 * - useVisualApprovalOsOverlay: sync native OS BBox overlay with pending desktop approvals
 *
 * [POS]
 * React lifecycle wrapper for §7 Tauri visual approval overlay.
 */

import { useEffect } from 'react';

import type { InspectorViewSnapshot } from '@/lib/approval/visualApprovalContext';
import { resolveDesktopOverlayTarget } from '@/lib/approval/resolveDesktopOverlayTarget';
import {
  hideVisualApprovalOsOverlay,
  showVisualApprovalOsOverlay,
} from '@/lib/approval/visualApprovalOsOverlay';
import {
  resetVisualApprovalOsOverlaySurface,
  setVisualApprovalOsOverlaySurface,
} from '@/lib/approval/visualApprovalOsOverlaySurface';
import { isTauriRuntime } from '@/lib/deploy-mode';
import type { ToolApprovalRequest } from '@/store/chat/types';

function logOverlayError(action: 'show' | 'hide', error: unknown): void {
  console.error(`[VisualApprovalOsOverlay] Failed to ${action} native overlay`, error);
}

export function useVisualApprovalOsOverlay(
  inlineRequests: ToolApprovalRequest[],
  desktopViewData: InspectorViewSnapshot | null,
  browserViewData: InspectorViewSnapshot | null,
  desktopLoading: boolean,
  browserLoading: boolean,
  snapshotFetchFailed: boolean,
): void {
  useEffect(() => {
    if (!isTauriRuntime()) {
      return;
    }

    const target = resolveDesktopOverlayTarget({
      inlineRequests,
      desktopViewData,
      browserViewData,
      desktopLoading,
      browserLoading,
      snapshotFetchFailed,
    });

    if (!target) {
      resetVisualApprovalOsOverlaySurface();
      void hideVisualApprovalOsOverlay().catch((error) => logOverlayError('hide', error));
      return;
    }

    void showVisualApprovalOsOverlay(target.payload)
      .then((result) => {
        if (!result) {
          resetVisualApprovalOsOverlaySurface();
          return;
        }
        const degraded = result.degraded || !result.shown;
        setVisualApprovalOsOverlaySurface({ degraded });
      })
      .catch((error) => {
        setVisualApprovalOsOverlaySurface({ degraded: true });
        logOverlayError('show', error);
      });
  }, [inlineRequests, desktopViewData, browserViewData, desktopLoading, browserLoading, snapshotFetchFailed]);

  useEffect(() => {
    if (!isTauriRuntime()) {
      return;
    }

    return () => {
      resetVisualApprovalOsOverlaySurface();
      void hideVisualApprovalOsOverlay().catch((error) => logOverlayError('hide', error));
    };
  }, []);
}
