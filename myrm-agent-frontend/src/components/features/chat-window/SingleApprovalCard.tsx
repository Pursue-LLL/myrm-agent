'use client';

import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';

import type { ToolApprovalRequest } from '@/store/chat/types';
import type { ToolApprovalResolveExtra } from '@/lib/approval/approvalDecision';
import EditModeView from './approval/EditModeView';
import RejectModeView from './approval/RejectModeView';
import HandoverModeView from './approval/HandoverModeView';
import AllowAlwaysConfirmDialog from './approval/AllowAlwaysConfirmDialog';
import ApprovalActions from './approval/ApprovalActions';
import ApprovalCountdown from './approval/ApprovalCountdown';
import ApprovalDetails from './approval/ApprovalDetails';
import GuidanceSection from './approval/GuidanceSection';
import PathGrantToggle from './approval/PathGrantToggle';
import OneTimeCredentialsSection from './approval/OneTimeCredentialsSection';
import { resolveBrowserSession } from '@/lib/approval/browserSession';
import { hasEditedChanges, initialEditedArgs, parseEditedArgs } from '@/lib/approval/editedArgs';
import { supportsOneTimeCredentials } from '@/lib/approval/oneTimeCredentials';
import { useApprovalCountdown } from '@/hooks/approval/useApprovalCountdown';
import { useStagedCredentials } from '@/hooks/approval/useStagedCredentials';
import {
  extractShellCommand,
  getShellEditInputEntries,
  isShellApprovalTool,
  mergeShellEditedArgs,
} from '@/lib/approval/shellCommandDisplay';
import {
  type AllowAlwaysDuration,
  type AllowAlwaysScope,
  defaultAllowAlwaysScope,
  durationToTtlSeconds,
  scopeToAllowAlwaysValue,
} from '@/lib/approval/allowAlwaysScope';
import { classifyApprovalSurface } from '@/lib/humanize';
import { isSaveSkillApproval } from '@/lib/approval/saveSkillApproval';
import { usePermissionAutoApprove } from './thinking-permission';

type DecisionType = 'approve' | 'edit' | 'reject';
type DialogMode = 'default' | 'editing' | 'rejecting';

interface SingleApprovalCardProps {
  request: ToolApprovalRequest;
  onResolve: (requestId: string, decision: DecisionType, extra?: ToolApprovalResolveExtra) => Promise<void>;
  isLoading: boolean;
  hideVisualHighlight?: boolean;
  compact?: boolean;
}

export default function SingleApprovalCard({
  request,
  onResolve,
  isLoading,
  hideVisualHighlight = false,
  compact = false,
}: SingleApprovalCardProps) {
  const t = useTranslations('toolApproval');
  const [mode, setMode] = useState<DialogMode>('default');
  const [editedArgs, setEditedArgs] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState('');
  const [showAlwaysAllowConfirm, setShowAlwaysAllowConfirm] = useState(false);
  const [allowAlwaysScope, setAllowAlwaysScope] = useState<AllowAlwaysScope>(() =>
    defaultAllowAlwaysScope(request.toolName),
  );
  const [allowAlwaysDuration, setAllowAlwaysDuration] = useState<AllowAlwaysDuration>('session');
  const [allowAlwaysInEdit, setAllowAlwaysInEdit] = useState(false);
  const [allowAlwaysScopeInEdit, setAllowAlwaysScopeInEdit] = useState<AllowAlwaysScope>(() =>
    defaultAllowAlwaysScope(request.toolName),
  );
  const [allowAlwaysDurationInEdit, setAllowAlwaysDurationInEdit] = useState<AllowAlwaysDuration>('session');
  const [editValidationErrors, setEditValidationErrors] = useState<string[]>([]);
  const [guidance, setGuidance] = useState('');
  const [guidanceOpen, setGuidanceOpen] = useState(false);
  const [grantDirectoryAccess, setGrantDirectoryAccess] = useState(false);

  const inputEntries = useMemo(() => {
    if (isShellApprovalTool(request.toolName)) {
      return getShellEditInputEntries(request.toolInput);
    }
    return Object.entries(request.toolInput).slice(0, 8);
  }, [request.toolInput, request.toolName]);

  const isSingleStringParam = inputEntries.length === 1 && typeof inputEntries[0][1] === 'string';

  const shellCommand = useMemo(
    () => (isShellApprovalTool(request.toolName) ? extractShellCommand(request.toolInput) : ''),
    [request.toolInput, request.toolName],
  );

  const credentials = useStagedCredentials({
    chatId: request.chatId,
    command: shellCommand,
    onExpired: () => toast.warning(t('maskedCredentials.toastExpired')),
  });

  const editedShellCommand = useMemo(
    () => (isShellApprovalTool(request.toolName) ? extractShellCommand(editedArgs as Record<string, unknown>) : ''),
    [editedArgs, request.toolName],
  );

  const browserSession = useMemo(
    () => resolveBrowserSession(request.toolName, request.toolInput),
    [request.toolInput, request.toolName],
  );

  const isSaveSkill = isSaveSkillApproval(request.toolName, request.toolInput);

  const isCompactSurface = compact || classifyApprovalSurface(request.toolName) === 'compact';

  const hideCompactPayload =
    isCompactSurface && !shellCommand && classifyApprovalSurface(request.toolName) === 'compact';

  const permissionTypeLabel =
    request.toolName === 'bash_code_execute_tool' || request.toolName === 'execute_code'
      ? t('permissionTypes.codeInterpreter')
      : request.toolName.startsWith('browser_')
        ? t('permissionTypes.browser')
        : t('permissionTypes.default');

  useEffect(() => {
    setEditedArgs(initialEditedArgs(inputEntries));
  }, [inputEntries]);

  useEffect(() => {
    const nextScope = defaultAllowAlwaysScope(request.toolName);
    setAllowAlwaysScope(nextScope);
    setAllowAlwaysScopeInEdit(nextScope);
  }, [request.requestId, request.toolName]);

  const { remainingSeconds, isExpired, isUrgent, progressPercent } = useApprovalCountdown(
    request.expiresAt,
    request.timeoutSeconds,
  );
  const isHandover = request.displayMode === 'handover';

  const guidanceExtra = useMemo(() => {
    const trimmed = guidance.trim();
    return trimmed ? { guidance: trimmed } : undefined;
  }, [guidance]);

  const directoryGrantExtra = useMemo(
    () =>
      grantDirectoryAccess && request.grantDirectories ? { grant_directories: request.grantDirectories } : undefined,
    [request.grantDirectories, grantDirectoryAccess],
  );

  const handleApprove = useCallback(
    async () =>
      await onResolve(request.requestId, 'approve', {
        ...guidanceExtra,
        ...directoryGrantExtra,
      }),
    [request.requestId, onResolve, guidanceExtra, directoryGrantExtra],
  );

  const { isHighRiskIntercepted, isAutoApproved } = usePermissionAutoApprove({
    toolName: request.toolName,
    toolInput: request.toolInput,
    onApprove: handleApprove,
    enabled: mode === 'default' && !isLoading && !isExpired,
  });

  const handleAlwaysAllow = useCallback(() => {
    setShowAlwaysAllowConfirm(true);
  }, []);

  const handleAllowDomain = useCallback(
    async () => await onResolve(request.requestId, 'approve', { allow_domain: true }),
    [request.requestId, onResolve],
  );

  const handleConfirmAlwaysAllow = useCallback(async () => {
    setShowAlwaysAllowConfirm(false);
    const ttlSeconds = durationToTtlSeconds(allowAlwaysDuration);
    await onResolve(request.requestId, 'approve', {
      allow_always: scopeToAllowAlwaysValue(allowAlwaysScope, allowAlwaysDuration),
      ttl_seconds: ttlSeconds,
    });
  }, [allowAlwaysDuration, allowAlwaysScope, request.requestId, onResolve]);

  const handleConfirmEdit = useCallback(async () => {
    const { parsed, invalidFields } = parseEditedArgs(editedArgs);

    if (invalidFields.length > 0) {
      setEditValidationErrors(invalidFields);
      toast.error(t('editValidationError', { fields: invalidFields.join(', ') }));
      return;
    }

    setEditValidationErrors([]);

    const ttlSeconds = allowAlwaysInEdit ? durationToTtlSeconds(allowAlwaysDurationInEdit) : undefined;
    const allowAlwaysValue = !allowAlwaysInEdit
      ? false
      : scopeToAllowAlwaysValue(allowAlwaysScopeInEdit, allowAlwaysDurationInEdit);

    const guidanceValue = guidance.trim() || undefined;
    if (hasEditedChanges(inputEntries, editedArgs)) {
      const editedArgsPayload = shellCommand ? mergeShellEditedArgs(request.toolInput, parsed) : parsed;
      if (credentials.staged && extractShellCommand(editedArgsPayload).trim() !== shellCommand.trim()) {
        credentials.discard();
        toast.info(t('maskedCredentials.droppedOnEdit'));
      }
      await onResolve(request.requestId, 'edit', {
        edited_args: editedArgsPayload,
        allow_always: allowAlwaysValue,
        ttl_seconds: ttlSeconds,
        guidance: guidanceValue,
      });
    } else {
      await onResolve(request.requestId, 'approve', {
        allow_always: allowAlwaysValue || undefined,
        ttl_seconds: ttlSeconds,
        guidance: guidanceValue,
      });
    }
    setAllowAlwaysInEdit(false);
    setAllowAlwaysScopeInEdit(defaultAllowAlwaysScope(request.toolName));
    setAllowAlwaysDurationInEdit('session');
  }, [
    editedArgs,
    inputEntries,
    allowAlwaysDurationInEdit,
    allowAlwaysInEdit,
    allowAlwaysScopeInEdit,
    guidance,
    request.requestId,
    request.toolInput,
    request.toolName,
    shellCommand,
    credentials,
    onResolve,
    t,
  ]);

  const handleConfirmReject = useCallback(async () => {
    credentials.discard();
    await onResolve(request.requestId, 'reject', { feedback: feedback || undefined });
  }, [credentials, feedback, request.requestId, onResolve]);

  if (mode === 'editing') {
    return (
      <EditModeView
        editedArgs={editedArgs}
        setEditedArgs={setEditedArgs}
        inputEntries={inputEntries}
        isSingleStringParam={isSingleStringParam}
        editValidationErrors={editValidationErrors}
        allowAlwaysInEdit={allowAlwaysInEdit}
        setAllowAlwaysInEdit={setAllowAlwaysInEdit}
        allowAlwaysScopeInEdit={allowAlwaysScopeInEdit}
        setAllowAlwaysScopeInEdit={setAllowAlwaysScopeInEdit}
        allowAlwaysDurationInEdit={allowAlwaysDurationInEdit}
        setAllowAlwaysDurationInEdit={setAllowAlwaysDurationInEdit}
        permissionTypeLabel={permissionTypeLabel}
        toolName={request.toolName}
        shellCommand={editedShellCommand}
        requestId={request.requestId}
        onConfirm={handleConfirmEdit}
        onCancel={() => {
          setMode('default');
          setAllowAlwaysInEdit(false);
          setEditValidationErrors([]);
        }}
        isLoading={isLoading}
        isExpired={isExpired}
        hideAllowAlways={request.hideAllowAlways}
      />
    );
  }

  if (mode === 'rejecting') {
    return (
      <RejectModeView
        feedback={feedback}
        setFeedback={setFeedback}
        onConfirm={handleConfirmReject}
        onCancel={() => setMode('default')}
        isLoading={isLoading}
        isExpired={isExpired}
      />
    );
  }

  if (isHandover) {
    const prompt = String(request.toolInput.value ?? '');
    return (
      <HandoverModeView
        prompt={prompt}
        onApprove={handleApprove}
        onReject={async () => await onResolve(request.requestId, 'reject', { feedback: 'User cancelled handover.' })}
        isLoading={isLoading}
      />
    );
  }

  return (
    <div className={`space-y-3 ${isCompactSurface ? 'p-2' : 'rounded-lg border p-4'}`}>
      <ApprovalDetails
        request={request}
        browserSession={browserSession}
        shellCommand={shellCommand}
        inputEntries={inputEntries}
        isSaveSkill={isSaveSkill}
        isHighRiskIntercepted={isHighRiskIntercepted}
        hideVisualHighlight={hideVisualHighlight}
        hideCompactPayload={hideCompactPayload}
      />

      <ApprovalCountdown
        remainingSeconds={remainingSeconds}
        isExpired={isExpired}
        isUrgent={isUrgent}
        progressPercent={progressPercent}
      />

      <GuidanceSection value={guidance} onChange={setGuidance} open={guidanceOpen} onOpenChange={setGuidanceOpen} />

      {!request.smartDenied && request.grantDirectories && (
        <PathGrantToggle
          directories={request.grantDirectories}
          checked={grantDirectoryAccess}
          onCheckedChange={setGrantDirectoryAccess}
          disabled={isLoading || isExpired}
        />
      )}

      {!request.smartDenied && shellCommand && supportsOneTimeCredentials(request.toolName) && (
        <OneTimeCredentialsSection
          staged={credentials.staged}
          onStage={credentials.stage}
          onRevoke={credentials.revoke}
          disabled={isLoading || isExpired}
        />
      )}

      <ApprovalActions
        request={request}
        isLoading={isLoading}
        isExpired={isExpired}
        isAutoApproved={isAutoApproved}
        isSaveSkill={isSaveSkill}
        onApprove={handleApprove}
        onEdit={() => setMode('editing')}
        onReject={() => setMode('rejecting')}
        onAlwaysAllow={handleAlwaysAllow}
        onAllowDomain={handleAllowDomain}
      />

      <AllowAlwaysConfirmDialog
        open={showAlwaysAllowConfirm}
        onOpenChange={setShowAlwaysAllowConfirm}
        allowAlwaysScope={allowAlwaysScope}
        setAllowAlwaysScope={setAllowAlwaysScope}
        allowAlwaysDuration={allowAlwaysDuration}
        setAllowAlwaysDuration={setAllowAlwaysDuration}
        permissionTypeLabel={permissionTypeLabel}
        toolName={request.toolName}
        shellCommand={shellCommand}
        onConfirm={handleConfirmAlwaysAllow}
        isLoading={isLoading}
      />
    </div>
  );
}
