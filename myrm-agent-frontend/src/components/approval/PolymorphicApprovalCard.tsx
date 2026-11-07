'use client';

import { useCallback, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Textarea } from '@/components/primitives/textarea';
import EditModeView from '@/components/features/chat-window/approval/EditModeView';
import AllowAlwaysConfirmDialog from '@/components/features/chat-window/approval/AllowAlwaysConfirmDialog';
import { durationToTtlSeconds, scopeToAllowAlwaysValue } from '@/lib/approval/allowAlwaysScope';
import type { ApprovalPayload } from '@/store/useApprovalStore';
import { DestructiveConfirmationBanner } from '@/components/approval/DestructiveConfirmationBanner';
import { ApprovalActions } from './polymorphic-card/ApprovalActions';
import {
  AutoModeSuspendedBanner,
  SmartDeniedBanner,
  SociallyIrreversibleBanner,
  SpendProtectionBanner,
} from './polymorphic-card/ApprovalBanners';
import { ApprovalContent } from './polymorphic-card/ApprovalContent';
import { ApprovalMetaBar } from './polymorphic-card/ApprovalMetaBar';
import { deriveApprovalFlags } from './polymorphic-card/approvalFlags';
import type { ApprovalResolveHandler } from './polymorphic-card/types';
import { useAllowAlwaysChoice } from './polymorphic-card/useAllowAlwaysChoice';
import { useShellEdit } from './polymorphic-card/useShellEdit';

interface PolymorphicApprovalCardProps {
  approval: ApprovalPayload;
  onResolve: ApprovalResolveHandler;
  isSubmitting: boolean;
}

/** One pending approval: the review that fits its action type, a comment, and the decision (approve, reject, edit or always allow). */
export function PolymorphicApprovalCard({ approval, onResolve, isSubmitting }: PolymorphicApprovalCardProps) {
  const t = useTranslations('toolApproval');
  const toolCalls = useMemo(() => approval.payload?.tool_calls ?? [], [approval.payload?.tool_calls]);
  const primaryToolName = toolCalls[0]?.name ?? 'unknown';

  const [comment, setComment] = useState('');
  const [showAlwaysAllowConfirm, setShowAlwaysAllowConfirm] = useState(false);
  const {
    scope: allowAlwaysScope,
    setScope: setAllowAlwaysScope,
    duration: allowAlwaysDuration,
    setDuration: setAllowAlwaysDuration,
  } = useAllowAlwaysChoice(approval.approval_id, primaryToolName);
  const [editedArgs, setEditedArgs] = useState<string>(() => {
    if (approval.action_type === 'tool_clarification') {
      return JSON.stringify(approval.payload?.content || {}, null, 2);
    }
    return '';
  });
  const [destructiveConfirmed, setDestructiveConfirmed] = useState(false);
  const isSubagentApproval = approval.action_type === 'subagent_approval';
  const flags = useMemo(() => deriveApprovalFlags(approval.payload), [approval.payload]);
  const shell = useShellEdit({
    approvalId: approval.approval_id,
    toolCalls,
    isSubagentApproval,
    primaryToolName,
    comment,
    onResolve,
  });

  const permissionTypeLabel = useMemo(() => {
    if (primaryToolName === 'bash_code_execute_tool' || primaryToolName === 'execute_code') {
      return t('permissionTypes.codeInterpreter');
    }
    if (primaryToolName.startsWith('browser_')) {
      return t('permissionTypes.browser');
    }
    return t('permissionTypes.default');
  }, [primaryToolName, t]);

  const handleConfirmAlwaysAllow = useCallback(async () => {
    setShowAlwaysAllowConfirm(false);
    const ttlSeconds = durationToTtlSeconds(allowAlwaysDuration);
    await onResolve('approve', comment, undefined, {
      allow_always: scopeToAllowAlwaysValue(allowAlwaysScope, allowAlwaysDuration),
      ttl_seconds: ttlSeconds,
      guidance: comment || undefined,
    });
  }, [allowAlwaysDuration, allowAlwaysScope, comment, onResolve]);

  const subagentTaskId = approval.payload?.subagent_task_id || approval.subagent_task_id;

  if (shell.isEditing && shell.singleShellToolCall) {
    return (
      <div className="space-y-6" data-subagent-task-id={subagentTaskId}>
        <EditModeView
          {...shell.editView}
          permissionTypeLabel={permissionTypeLabel}
          toolName={shell.singleShellToolCall.name}
          hideAllowAlways={flags.hasAnyHideAllowAlways}
          requestId={approval.approval_id}
          isLoading={isSubmitting}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-subagent-task-id={subagentTaskId}>
      <ApprovalMetaBar chatId={approval.chat_id} expiresAt={approval.expires_at} />

      <ApprovalContent approval={approval} editedArgs={editedArgs} onEditedArgsChange={setEditedArgs} />

      {flags.spendConfig && <SpendProtectionBanner spendConfig={flags.spendConfig} />}

      {flags.autoModeSuspendedBreach && (
        <AutoModeSuspendedBanner autoModeSuspendedBreach={flags.autoModeSuspendedBreach} />
      )}

      {flags.isIrreversibleDestructive && (
        <DestructiveConfirmationBanner
          blastRadius={flags.destructiveBlastRadius}
          snapshotId={flags.destructiveSnapshotId}
          onConfirmationChange={setDestructiveConfirmed}
          disabled={isSubmitting}
        />
      )}

      {flags.isSociallyIrreversible && <SociallyIrreversibleBanner />}

      {flags.hasAnySmartDenied && <SmartDeniedBanner />}

      <div className="space-y-2">
        <label htmlFor={`comment-${approval.approval_id}`} className="text-sm font-medium">
          {t('commentsOptional')}
        </label>
        <Textarea
          id={`comment-${approval.approval_id}`}
          placeholder={t('addCommentPlaceholder')}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={3}
        />
      </div>

      <ApprovalActions
        approval={approval}
        comment={comment}
        editedArgs={editedArgs}
        flags={flags}
        destructiveConfirmed={destructiveConfirmed}
        isSubmitting={isSubmitting}
        canEditShell={shell.singleShellToolCall !== null}
        canAllowAlways={isSubagentApproval && !flags.hasAnyHideAllowAlways}
        onResolve={onResolve}
        onEdit={shell.startEditing}
        onAllowAlways={() => setShowAlwaysAllowConfirm(true)}
      />

      {isSubagentApproval && (
        <AllowAlwaysConfirmDialog
          open={showAlwaysAllowConfirm}
          onOpenChange={setShowAlwaysAllowConfirm}
          allowAlwaysScope={allowAlwaysScope}
          setAllowAlwaysScope={setAllowAlwaysScope}
          allowAlwaysDuration={allowAlwaysDuration}
          setAllowAlwaysDuration={setAllowAlwaysDuration}
          permissionTypeLabel={permissionTypeLabel}
          toolName={primaryToolName}
          shellCommand={shell.shellCommand}
          onConfirm={handleConfirmAlwaysAllow}
          isLoading={isSubmitting}
        />
      )}
    </div>
  );
}
