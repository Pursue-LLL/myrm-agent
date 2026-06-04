'use client';

import { useMemo } from 'react';

import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import { hasVisualApprovalContext } from '@/lib/approval/visualApprovalContext';
import { useToolApprovalResolve } from '@/hooks/useToolApprovalResolve';
import VisualApprovalArtifactCard from './VisualApprovalArtifactCard';

interface VisualApprovalInlineSectionProps {
  messageId: string;
  chatId: string | null;
}

export default function VisualApprovalInlineSection({ messageId, chatId }: VisualApprovalInlineSectionProps) {
  const queue = useToolApprovalStore((state) => state.queue);
  const desktopViewData = useDesktopInspectorStore((state) => state.viewData);
  const browserViewData = useBrowserInspectorStore((state) => state.viewData);
  const { resolveRequest, isLoading } = useToolApprovalResolve();

  const visualRequests = useMemo(() => {
    if (!chatId) {
      return [];
    }

    return queue.filter(
      (request) =>
        request.messageId === messageId &&
        request.chatId === chatId &&
        hasVisualApprovalContext(request, desktopViewData, browserViewData),
    );
  }, [browserViewData, chatId, desktopViewData, messageId, queue]);

  if (visualRequests.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3" data-testid="visual-approval-inline-section">
      {visualRequests.map((request) => (
        <VisualApprovalArtifactCard
          key={request.requestId}
          request={request}
          desktopViewData={desktopViewData}
          browserViewData={browserViewData}
          onResolve={resolveRequest}
          isLoading={isLoading}
        />
      ))}
    </div>
  );
}
