/**
 * [INPUT]
 * - @/lib/approval/visualApprovalContext::VisualApprovalContext (POS: BBox viewport context)
 * - @/lib/tauri::invokeTauriCommand (POS: Tauri IPC bridge)
 * - @/lib/deploy-mode::isTauriRuntime (POS: Tauri runtime detection)
 *
 * [OUTPUT]
 * - buildVisualApprovalOsOverlayPayload: maps visual context to Tauri overlay IPC payload
 * - showVisualApprovalOsOverlay / hideVisualApprovalOsOverlay: native OS highlight control
 *
 * [POS]
 * Desktop-only bridge for §7 Tauri visual approval overlay (host screen red frame).
 */

import type { VisualApprovalContext } from '@/lib/approval/visualApprovalContext';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { invokeTauriCommand } from '@/lib/tauri';

export interface VisualApprovalOsOverlayPayload {
  x: number;
  y: number;
  width: number;
  height: number;
  viewportWidth: number;
  viewportHeight: number;
  label?: string;
}

export function buildVisualApprovalOsOverlayPayload(
  context: VisualApprovalContext,
): VisualApprovalOsOverlayPayload {
  return {
    x: context.bbox.x,
    y: context.bbox.y,
    width: context.bbox.width,
    height: context.bbox.height,
    viewportWidth: context.viewportWidth,
    viewportHeight: context.viewportHeight,
    label: context.targetLabel,
  };
}

export async function showVisualApprovalOsOverlay(payload: VisualApprovalOsOverlayPayload): Promise<void> {
  if (!isTauriRuntime()) {
    return;
  }

  await invokeTauriCommand('show_visual_approval_overlay', { payload });
}

export async function hideVisualApprovalOsOverlay(): Promise<void> {
  if (!isTauriRuntime()) {
    return;
  }

  await invokeTauriCommand('hide_visual_approval_overlay');
}
