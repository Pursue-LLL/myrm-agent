'use client';

import { useTranslations } from 'next-intl';
import { AlertTriangle, Pencil } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { DestructiveUndoCard } from '@/components/approval/DestructiveUndoCard';
import type { ApprovalPayload } from '@/store/useApprovalStore';
import type { ApprovalFlags } from './approvalFlags';
import type { ApprovalResolveHandler } from './types';

interface ApprovalActionsProps {
  approval: ApprovalPayload;
  comment: string;
  /** The tool-clarification editor's text; sent as the edited payload when the user approves a retry. */
  editedArgs: string;
  flags: ApprovalFlags;
  destructiveConfirmed: boolean;
  isSubmitting: boolean;
  canEditShell: boolean;
  canAllowAlways: boolean;
  onResolve: ApprovalResolveHandler;
  onEdit: () => void;
  onAllowAlways: () => void;
}

/** Reject / edit / always allow / approve. An irreversible action stays locked until the user has confirmed it. */
export function ApprovalActions({
  approval,
  comment,
  editedArgs,
  flags,
  destructiveConfirmed,
  isSubmitting,
  canEditShell,
  canAllowAlways,
  onResolve,
  onEdit,
  onAllowAlways,
}: ApprovalActionsProps) {
  const t = useTranslations('toolApproval');
  const { hasAnySmartDenied, isIrreversibleDestructive, destructiveSnapshotId, spendConfig } = flags;
  return (
    <div className="flex flex-wrap items-center justify-end gap-3 pt-4 border-t">
      {hasAnySmartDenied ? (
        <>
          <Button
            variant="destructive"
            onClick={() => onResolve('reject', comment, undefined, { feedback: comment || undefined })}
            disabled={isSubmitting}
          >
            {t('reject')}
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              onResolve('approve', comment, undefined, {
                guidance: comment || undefined,
                action_digest: spendConfig?.actionDigest,
                actionDigest: spendConfig?.actionDigest,
              });
            }}
            disabled={isSubmitting || (isIrreversibleDestructive && !destructiveConfirmed)}
          >
            <AlertTriangle className="mr-1 h-3.5 w-3.5" />
            {t('smartDenied.overrideOnce')}
          </Button>
        </>
      ) : (
        <>
          <Button
            variant="outline"
            onClick={() => onResolve('reject', comment, undefined, { feedback: comment || undefined })}
            disabled={isSubmitting}
          >
            {t('reject')}
          </Button>
          {canEditShell && (
            <Button variant="secondary" onClick={onEdit} disabled={isSubmitting}>
              <Pencil className="mr-1 h-3.5 w-3.5" />
              {t('edit')}
            </Button>
          )}
          {canAllowAlways && (
            <Button
              variant="ghost"
              onClick={onAllowAlways}
              disabled={isSubmitting}
              className="text-xs text-amber-600 hover:text-amber-700"
            >
              {t('allowAlways')}
            </Button>
          )}
          <Button
            variant={isIrreversibleDestructive ? 'destructive' : 'default'}
            onClick={() => {
              let edited_payload: Record<string, unknown> | undefined = undefined;
              if (approval.action_type === 'tool_clarification') {
                try {
                  edited_payload = JSON.parse(editedArgs);
                } catch {
                  console.error('Invalid JSON payload');
                  return;
                }
              }
              onResolve('approve', comment, edited_payload, {
                guidance: comment || undefined,
                action_digest: spendConfig?.actionDigest,
                actionDigest: spendConfig?.actionDigest,
              });
              if (isIrreversibleDestructive && destructiveSnapshotId) {
                toast.custom(
                  (toastId) => (
                    <DestructiveUndoCard
                      approvalId={approval.approval_id}
                      snapshotId={destructiveSnapshotId}
                      onRollbackSuccess={() => toast.dismiss(toastId)}
                    />
                  ),
                  {
                    duration: 10 * 60 * 1000,
                    id: `destructive-undo-${approval.approval_id}`,
                  },
                );
              }
            }}
            disabled={isSubmitting || (isIrreversibleDestructive && !destructiveConfirmed)}
          >
            {isIrreversibleDestructive ? t('irreversibleDestructive.confirmButton') : t('approve')}
          </Button>
        </>
      )}
    </div>
  );
}
