/**
 * [INPUT]
 * - show_visual_approval_overlay IPC result (POS: degraded when OS highlight unsafe)
 *
 * [OUTPUT]
 * - setVisualApprovalOsOverlaySurface / useVisualApprovalOsOverlaySurface
 *
 * [POS]
 * Lightweight cross-tree signal so chat approval cards reflect native overlay availability.
 */

'use client';

import { useSyncExternalStore } from 'react';

export interface VisualApprovalOsOverlaySurfaceState {
  degraded: boolean;
}

let surfaceState: VisualApprovalOsOverlaySurfaceState = { degraded: false };
const listeners = new Set<() => void>();

function emitSurfaceChange(): void {
  listeners.forEach((listener) => listener());
}

export function setVisualApprovalOsOverlaySurface(
  patch: Partial<VisualApprovalOsOverlaySurfaceState>,
): void {
  const next = { ...surfaceState, ...patch };
  if (next.degraded === surfaceState.degraded) {
    return;
  }
  surfaceState = next;
  emitSurfaceChange();
}

export function resetVisualApprovalOsOverlaySurface(): void {
  setVisualApprovalOsOverlaySurface({ degraded: false });
}

export function useVisualApprovalOsOverlaySurface(): VisualApprovalOsOverlaySurfaceState {
  return useSyncExternalStore(
    (onStoreChange) => {
      listeners.add(onStoreChange);
      return () => listeners.delete(onStoreChange);
    },
    () => surfaceState,
    () => surfaceState,
  );
}
