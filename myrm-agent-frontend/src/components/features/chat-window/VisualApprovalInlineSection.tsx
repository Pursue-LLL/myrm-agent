'use client';

import { useMemo } from 'react';

import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import { usesInlineVisualApprovalSurface } from '@/lib/approval/visualApprovalSurface';
import { useToolApprovalResolve } from '@/hooks/useToolApprovalResolve';
import { useVisualApprovalSnapshot } from '@/hooks/useVisualApprovalSnapshot';
import VisualApprovalRequestRenderer from './approval/VisualApprovalRequestRenderer';

interface VisualApprovalInlineSectionProps {
  messageId: string;
  chatId: string | null;
}

export default function VisualApprovalInlineSection({ messageId, chatId }: VisualApprovalInlineSectionProps) {
  const queue = useToolApprovalStore((state) => state.queue);
  const desktopViewData = useDesktopInspectorStore((state) => state.viewData);
  const browserViewData = useBrowserInspectorStore((state) => state.viewData);
  const desktopLoading = useDesktopInspectorStore((state) => state.isSnapshotLoading);
  const browserLoading = useBrowserInspectorStore((state) => state.isSnapshotLoading);
  const { resolveRequest, isLoading } = useToolApprovalResolve();

  const inlineRequests = useMemo(() => {
    if (!chatId) {
      return [];
    }

    return queue.filter(
      (request) =>
        request.messageId === messageId &&
        request.chatId === chatId &&
        usesInlineVisualApprovalSurface(request, queue),
    );
  }, [chatId, messageId, queue]);

  const { status, snapshotFetchFailed, retrySnapshot } = useVisualApprovalSnapshot(inlineRequests);
  const snapshotRetrying = status === 'loading';

  if (inlineRequests.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3" data-testid="visual-approval-inline-section">
      {inlineRequests.map((request) => (
        <VisualApprovalRequestRenderer
          key={request.requestId}
          request={request}
          desktopViewData={desktopViewData}
          browserViewData={browserViewData}
          desktopLoading={desktopLoading}
          browserLoading={browserLoading}
          snapshotFetchFailed={snapshotFetchFailed}
          snapshotRetrying={snapshotRetrying}
          onRetrySnapshot={retrySnapshot}
          onResolve={resolveRequest}
          isLoading={isLoading}
        />
      ))}
    </div>
  );
}
