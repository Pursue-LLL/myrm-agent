'use client';

import { useMemo } from 'react';

import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import {
  hasVisualApprovalContext,
  resolveVisualApprovalContextForRequest,
} from '@/lib/approval/visualApprovalContext';
import { usesInlineVisualApprovalSurface } from '@/lib/approval/visualApprovalSurface';
import { useToolApprovalResolve } from '@/hooks/useToolApprovalResolve';
import { useVisualApprovalSnapshot } from '@/hooks/useVisualApprovalSnapshot';
import VisualApprovalArtifactCard from './VisualApprovalArtifactCard';
import VisualApprovalPendingCard from './VisualApprovalPendingCard';

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

  useVisualApprovalSnapshot(inlineRequests);

  if (inlineRequests.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3" data-testid="visual-approval-inline-section">
      {inlineRequests.map((request) => {
        const visualContext = resolveVisualApprovalContextForRequest(request, desktopViewData, browserViewData);
        if (visualContext) {
          return (
            <VisualApprovalArtifactCard
              key={request.requestId}
              request={request}
              desktopViewData={desktopViewData}
              browserViewData={browserViewData}
              onResolve={resolveRequest}
              isLoading={isLoading}
            />
          );
        }

        const waitingForSnapshot =
          (request.toolName.startsWith('desktop_') && desktopLoading) ||
          (request.toolName.startsWith('browser_') && browserLoading) ||
          !hasVisualApprovalContext(request, desktopViewData, browserViewData);

        if (waitingForSnapshot) {
          return <VisualApprovalPendingCard key={request.requestId} request={request} />;
        }

        return null;
      })}
    </div>
  );
}
