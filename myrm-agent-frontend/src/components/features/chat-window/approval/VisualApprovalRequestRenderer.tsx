'use client';

import type { InspectorViewSnapshot } from '@/lib/approval/visualApprovalContext';
import { resolveVisualApprovalRenderState } from '@/lib/approval/visualApprovalRenderState';
import type { ToolApprovalRequest } from '@/store/chat/types';
import type { ToolApprovalResolveExtra } from '@/hooks/useToolApprovalResolve';
import VisualApprovalArtifactCard from '../VisualApprovalArtifactCard';
import VisualApprovalPendingCard from '../VisualApprovalPendingCard';
import VisualApprovalUnavailableCard from './VisualApprovalUnavailableCard';

type DecisionType = 'approve' | 'edit' | 'reject';

interface VisualApprovalRequestRendererProps {
  request: ToolApprovalRequest;
  desktopViewData: InspectorViewSnapshot | null;
  browserViewData: InspectorViewSnapshot | null;
  desktopLoading: boolean;
  browserLoading: boolean;
  snapshotFetchFailed: boolean;
  snapshotRetrying: boolean;
  onRetrySnapshot: () => void;
  onResolve: (
    requestId: string,
    decision: DecisionType,
    extra?: ToolApprovalResolveExtra,
  ) => Promise<void>;
  isLoading: boolean;
}

export default function VisualApprovalRequestRenderer({
  request,
  desktopViewData,
  browserViewData,
  desktopLoading,
  browserLoading,
  snapshotFetchFailed,
  snapshotRetrying,
  onRetrySnapshot,
  onResolve,
  isLoading,
}: VisualApprovalRequestRendererProps) {
  const renderState = resolveVisualApprovalRenderState({
    request,
    desktopViewData,
    browserViewData,
    desktopLoading: desktopLoading || snapshotRetrying,
    browserLoading: browserLoading || snapshotRetrying,
    snapshotFetchFailed,
  });

  if (renderState.phase === 'ready' && renderState.visualContext) {
    return (
      <VisualApprovalArtifactCard
        request={request}
        desktopViewData={desktopViewData}
        browserViewData={browserViewData}
        onResolve={onResolve}
        isLoading={isLoading}
      />
    );
  }

  if (renderState.phase === 'loading') {
    return <VisualApprovalPendingCard request={request} />;
  }

  return (
    <VisualApprovalUnavailableCard
      request={request}
      reason={renderState.unavailableReason ?? 'fetch_failed'}
      onRetrySnapshot={onRetrySnapshot}
      onResolve={onResolve}
      isLoading={isLoading}
      isRetrying={snapshotRetrying}
    />
  );
}
