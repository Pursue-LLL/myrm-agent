'use client';

import { useTranslations } from 'next-intl';
import { AlertCircle, RefreshCw, ShieldAlert } from 'lucide-react';

import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import type { VisualApprovalUnavailableReason } from '@/lib/approval/visualApprovalRenderState';
import type { ToolApprovalRequest } from '@/store/chat/types';
import SingleApprovalCard from '../SingleApprovalCard';
import type { ToolApprovalResolveExtra } from '@/hooks/useToolApprovalResolve';

type DecisionType = 'approve' | 'edit' | 'reject';

interface VisualApprovalUnavailableCardProps {
  request: ToolApprovalRequest;
  reason: VisualApprovalUnavailableReason;
  onRetrySnapshot: () => void;
  onResolve: (
    requestId: string,
    decision: DecisionType,
    extra?: ToolApprovalResolveExtra,
  ) => Promise<void>;
  isLoading: boolean;
  isRetrying: boolean;
}

export default function VisualApprovalUnavailableCard({
  request,
  reason,
  onRetrySnapshot,
  onResolve,
  isLoading,
  isRetrying,
}: VisualApprovalUnavailableCardProps) {
  const t = useTranslations('toolApproval');

  const messageKey =
    reason === 'permission'
      ? 'visualApprovalUnavailablePermission'
      : reason === 'missing_target'
        ? 'visualApprovalUnavailableMissingTarget'
        : 'visualApprovalUnavailableFetchFailed';

  return (
    <div
      className="overflow-hidden rounded-xl border-2 border-amber-500/30 bg-gradient-to-b from-amber-500/10 to-background shadow-sm"
      data-testid="visual-approval-unavailable-card"
    >
      <div className="flex flex-wrap items-center gap-2 border-b border-amber-500/20 px-4 py-3">
        <ShieldAlert className="h-4 w-4 text-amber-600 dark:text-amber-400" />
        <span className="text-sm font-semibold text-foreground">{t('visualApprovalArtifactTitle')}</span>
        <Badge variant="secondary" className="font-mono text-[10px]">
          {request.toolName}
        </Badge>
      </div>

      <div className="space-y-3 px-4 py-4">
        <div className="flex items-start gap-2 text-sm text-muted-foreground">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
          <p>{t(messageKey)}</p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-8"
          onClick={onRetrySnapshot}
          disabled={isRetrying || isLoading}
        >
          <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${isRetrying ? 'animate-spin' : ''}`} />
          {t('visualApprovalRetrySnapshot')}
        </Button>
        <p className="text-xs text-muted-foreground">{t('visualApprovalFallbackHint')}</p>
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
