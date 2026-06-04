'use client';

/**
 * [INPUT] Pending visual approval request without resolved screenshot context
 * [OUTPUT] Loading placeholder card while snapshot fetch runs
 * [POS] Empty-state UI for inline visual approvals
 */

import { useTranslations } from 'next-intl';
import { Loader2, ShieldAlert } from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import type { ToolApprovalRequest } from '@/store/chat/types';

interface VisualApprovalPendingCardProps {
  request: ToolApprovalRequest;
}

export default function VisualApprovalPendingCard({ request }: VisualApprovalPendingCardProps) {
  const t = useTranslations('toolApproval');

  return (
    <div
      className="overflow-hidden rounded-xl border-2 border-amber-500/30 bg-gradient-to-b from-amber-500/10 to-background shadow-sm"
      data-testid="visual-approval-pending-card"
    >
      <div className="flex flex-wrap items-center gap-2 border-b border-amber-500/20 px-4 py-3">
        <ShieldAlert className="h-4 w-4 text-amber-600 dark:text-amber-400" />
        <span className="text-sm font-semibold text-foreground">{t('visualApprovalArtifactTitle')}</span>
        <Badge variant="secondary" className="font-mono text-[10px]">
          {request.toolName}
        </Badge>
      </div>
      <div className="flex min-h-[160px] flex-col items-center justify-center gap-3 px-4 py-8 text-center sm:min-h-[200px]">
        <Loader2 className="h-6 w-6 animate-spin text-amber-500" />
        <p className="max-w-sm text-xs text-muted-foreground sm:text-sm">{t('visualApprovalLoadingSnapshot')}</p>
      </div>
    </div>
  );
}
