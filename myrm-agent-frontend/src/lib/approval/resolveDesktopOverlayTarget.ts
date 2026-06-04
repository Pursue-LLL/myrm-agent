/**
 * [INPUT]
 * - @/lib/approval/visualApprovalRenderState (POS: loading/ready/unavailable phase)
 * - @/lib/approval/visualApprovalOsOverlay (POS: Tauri overlay IPC payload)
 * - pending inline desktop visual approval requests + inspector snapshots
 *
 * [OUTPUT]
 * - selectEarliestInlineRequest: earliest-expiring inline HITL request
 * - resolveDesktopOverlayTarget: ready desktop overlay request + payload
 *
 * [POS]
 * Single source of truth for AttentionBar primary request and Tauri OS overlay target.
 */

import {
  buildVisualApprovalOsOverlayPayload,
  type VisualApprovalOsOverlayPayload,
} from '@/lib/approval/visualApprovalOsOverlay';
import type { InspectorViewSnapshot } from '@/lib/approval/visualApprovalContext';
import { resolveVisualApprovalRenderState } from '@/lib/approval/visualApprovalRenderState';
import type { ToolApprovalRequest } from '@/store/chat/types';

export interface DesktopOverlayTargetInput {
  inlineRequests: ToolApprovalRequest[];
  desktopViewData: InspectorViewSnapshot | null;
  browserViewData: InspectorViewSnapshot | null;
  desktopLoading: boolean;
  browserLoading: boolean;
  snapshotFetchFailed: boolean;
}

export interface DesktopOverlayTarget {
  request: ToolApprovalRequest;
  payload: VisualApprovalOsOverlayPayload;
}

export function selectEarliestInlineRequest(
  inlineRequests: ToolApprovalRequest[],
): ToolApprovalRequest | undefined {
  if (inlineRequests.length === 0) {
    return undefined;
  }

  return [...inlineRequests].sort((left, right) => left.expiresAt - right.expiresAt)[0];
}

export function resolveDesktopOverlayTarget(
  input: DesktopOverlayTargetInput,
): DesktopOverlayTarget | null {
  const desktopRequests = input.inlineRequests
    .filter((request) => request.toolName.startsWith('desktop_'))
    .sort((left, right) => left.expiresAt - right.expiresAt);

  for (const request of desktopRequests) {
    const renderState = resolveVisualApprovalRenderState({
      request,
      desktopViewData: input.desktopViewData,
      browserViewData: input.browserViewData,
      desktopLoading: input.desktopLoading,
      browserLoading: input.browserLoading,
      snapshotFetchFailed: input.snapshotFetchFailed,
    });

    if (renderState.phase !== 'ready' || !renderState.visualContext) {
      continue;
    }

    return {
      request,
      payload: buildVisualApprovalOsOverlayPayload(renderState.visualContext),
    };
  }

  return null;
}
