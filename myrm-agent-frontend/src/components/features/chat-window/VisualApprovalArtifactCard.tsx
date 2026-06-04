'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { Crosshair, ShieldAlert, Target } from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import {
  resolveVisualApprovalContextForRequest,
  type InspectorViewSnapshot,
} from '@/lib/approval/visualApprovalContext';
import { formatSnapshotAgeSeconds } from '@/lib/approval/visualApprovalRenderState';
import type { ToolApprovalRequest } from '@/store/chat/types';
import VisualApprovalHighlight from './approval/VisualApprovalHighlight';
import SingleApprovalCard from './SingleApprovalCard';
import type { ToolApprovalResolveExtra } from '@/hooks/useToolApprovalResolve';

type DecisionType = 'approve' | 'edit' | 'reject';

interface VisualApprovalArtifactCardProps {
  request: ToolApprovalRequest;
  desktopViewData: InspectorViewSnapshot | null;
  browserViewData: InspectorViewSnapshot | null;
  onResolve: (
    requestId: string,
    decision: DecisionType,
    extra?: ToolApprovalResolveExtra,
  ) => Promise<void>;
  isLoading: boolean;
}

export default function VisualApprovalArtifactCard({
  request,
  desktopViewData,
  browserViewData,
  onResolve,
  isLoading,
}: VisualApprovalArtifactCardProps) {
  const t = useTranslations('toolApproval');

  const visualContext = useMemo(
    () => resolveVisualApprovalContextForRequest(request, desktopViewData, browserViewData),
    [browserViewData, desktopViewData, request],
  );

  if (!visualContext) {
    return null;
  }

  const targetHint =
    visualContext.highlightKind === 'coordinate'
      ? t('visualApprovalCoordinateTarget', { label: visualContext.targetLabel ?? '' })
      : t('visualApprovalRefTarget', { label: visualContext.targetLabel ?? '' });

  const snapshotViewData = request.toolName.startsWith('desktop_') ? desktopViewData : browserViewData;
  const snapshotAgeSeconds = formatSnapshotAgeSeconds(snapshotViewData?.updatedAt, Date.now());

  return (
    <div
      className="overflow-hidden rounded-xl border-2 border-amber-500/40 bg-gradient-to-b from-amber-500/10 to-background shadow-sm"
      data-testid="visual-approval-artifact-card"
    >
      <div className="flex flex-wrap items-center gap-2 border-b border-amber-500/20 px-4 py-3">
        <ShieldAlert className="h-4 w-4 text-amber-600 dark:text-amber-400" />
        <span className="text-sm font-semibold text-foreground">{t('visualApprovalArtifactTitle')}</span>
        <Badge variant="secondary" className="font-mono text-[10px]">
          {request.toolName}
        </Badge>
      </div>

      <div className="space-y-3 px-4 py-3">
        <p className="text-xs text-muted-foreground">{t('visualApprovalArtifactDescription')}</p>

        <VisualApprovalHighlight visualContext={visualContext} maxHeight={360} />

        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {visualContext.highlightKind === 'coordinate' ? (
            <Crosshair className="h-3.5 w-3.5 text-red-500" />
          ) : (
            <Target className="h-3.5 w-3.5 text-red-500" />
          )}
          <span>{targetHint}</span>
          {snapshotAgeSeconds !== null && (
            <span className="text-[11px] text-muted-foreground/80">
              {t('visualApprovalSnapshotAge', { seconds: snapshotAgeSeconds })}
            </span>
          )}
        </div>
      </div>

      <div className="border-t border-amber-500/20 bg-background/80 px-2 py-2">
        <SingleApprovalCard
          request={request}
          onResolve={onResolve}
          isLoading={isLoading}
          hideVisualHighlight
          compact
        />
      </div>
    </div>
  );
}
