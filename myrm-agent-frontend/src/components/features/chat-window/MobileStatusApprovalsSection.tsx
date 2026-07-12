'use client';

import { ShieldCheck, ShieldX } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import VisualApprovalRequestRenderer from '@/components/features/chat-window/approval/VisualApprovalRequestRenderer';
import SingleApprovalCard from '@/components/features/chat-window/SingleApprovalCard';
import type { ToolApprovalRequest } from '@/store/chat/types';
import type { InspectorViewSnapshot } from '@/lib/approval/visualApprovalContext';
import type { ToolApprovalResolveExtra } from '@/hooks/useToolApprovalResolve';

type DecisionType = 'approve' | 'edit' | 'reject';

interface MobileStatusApprovalsSectionProps {
  pendingCount: number;
  inlineRequests: ToolApprovalRequest[];
  modalRequests: ToolApprovalRequest[];
  desktopViewData: InspectorViewSnapshot | null;
  browserViewData: InspectorViewSnapshot | null;
  desktopLoading: boolean;
  browserLoading: boolean;
  snapshotFetchFailed: boolean;
  snapshotRetrying: boolean;
  onRetrySnapshot: () => void;
  onResolve: (requestId: string, decision: DecisionType, extra?: ToolApprovalResolveExtra) => Promise<void>;
  onApproveAll: (requests: ToolApprovalRequest[]) => Promise<void>;
  onRejectAll: (requests: ToolApprovalRequest[]) => Promise<void>;
  isApprovalLoading: boolean;
}

export function MobileStatusApprovalsSection({
  pendingCount,
  inlineRequests,
  modalRequests,
  desktopViewData,
  browserViewData,
  desktopLoading,
  browserLoading,
  snapshotFetchFailed,
  snapshotRetrying,
  onRetrySnapshot,
  onResolve,
  onApproveAll,
  onRejectAll,
  isApprovalLoading,
}: MobileStatusApprovalsSectionProps) {
  const t = useTranslations('agent.mobileCommand');
  const tToolApproval = useTranslations('toolApproval');

  if (pendingCount === 0) return null;

  return (
    <div className="bg-card rounded-2xl border border-amber-500/30 overflow-hidden">
      <div className="p-3 border-b bg-amber-500/10 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-amber-500" />
          <h2 className="text-sm font-medium">
            {t('pendingApprovals')} ({pendingCount})
          </h2>
        </div>
        {modalRequests.length > 1 && (
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={() => void onRejectAll(modalRequests)}
              disabled={isApprovalLoading}
            >
              <ShieldX className="mr-1 h-3.5 w-3.5" />
              {tToolApproval('rejectAll')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={() => void onApproveAll(modalRequests)}
              disabled={isApprovalLoading}
            >
              {t('approveAll')}
            </Button>
          </div>
        )}
      </div>
      <div className="divide-y space-y-3 p-3">
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
            onRetrySnapshot={onRetrySnapshot}
            onResolve={onResolve}
            isLoading={isApprovalLoading}
          />
        ))}
        {modalRequests.map((request) => (
          <SingleApprovalCard
            key={request.requestId}
            request={request}
            onResolve={onResolve}
            isLoading={isApprovalLoading}
            compact
            hideVisualHighlight
          />
        ))}
      </div>
    </div>
  );
}
