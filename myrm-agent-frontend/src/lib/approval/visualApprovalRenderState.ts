import {
  resolveVisualApprovalContextForRequest,
  type InspectorViewSnapshot,
} from '@/lib/approval/visualApprovalContext';
import type { ToolApprovalRequest } from '@/store/chat/types';

export type VisualApprovalRenderPhase = 'ready' | 'loading' | 'unavailable';

export type VisualApprovalUnavailableReason = 'permission' | 'fetch_failed' | 'missing_target';

export interface VisualApprovalRenderState {
  phase: VisualApprovalRenderPhase;
  visualContext: ReturnType<typeof resolveVisualApprovalContextForRequest>;
  unavailableReason?: VisualApprovalUnavailableReason;
}

interface VisualApprovalRenderInput {
  request: ToolApprovalRequest;
  desktopViewData: InspectorViewSnapshot | null;
  browserViewData: InspectorViewSnapshot | null;
  desktopLoading: boolean;
  browserLoading: boolean;
  snapshotFetchFailed: boolean;
}

export function resolveVisualApprovalRenderState({
  request,
  desktopViewData,
  browserViewData,
  desktopLoading,
  browserLoading,
  snapshotFetchFailed,
}: VisualApprovalRenderInput): VisualApprovalRenderState {
  const visualContext = resolveVisualApprovalContextForRequest(request, desktopViewData, browserViewData);
  if (visualContext) {
    return { phase: 'ready', visualContext };
  }

  const isDesktop = request.toolName.startsWith('desktop_');
  const isBrowser = request.toolName.startsWith('browser_');
  const isLoading = (isDesktop && desktopLoading) || (isBrowser && browserLoading);

  if (isLoading) {
    return { phase: 'loading', visualContext: null };
  }

  if (isDesktop && desktopViewData?.needsPermission) {
    return {
      phase: 'unavailable',
      visualContext: null,
      unavailableReason: 'permission',
    };
  }

  const activeViewData = isDesktop ? desktopViewData : isBrowser ? browserViewData : null;
  if (activeViewData?.screenshotBase64) {
    return {
      phase: 'unavailable',
      visualContext: null,
      unavailableReason: 'missing_target',
    };
  }

  return {
    phase: 'unavailable',
    visualContext: null,
    unavailableReason: 'fetch_failed',
  };
}

export function formatSnapshotAgeSeconds(updatedAt: number | undefined, nowMs: number): number | null {
  if (!updatedAt || updatedAt <= 0) {
    return null;
  }
  return Math.max(0, Math.floor((nowMs - updatedAt) / 1000));
}
