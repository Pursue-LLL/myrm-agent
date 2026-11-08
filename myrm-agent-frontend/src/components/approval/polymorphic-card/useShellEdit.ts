'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import {
  defaultAllowAlwaysScope,
  durationToTtlSeconds,
  scopeToAllowAlwaysValue,
} from '@/lib/approval/allowAlwaysScope';
import {
  extractShellCommand,
  getShellEditInputEntries,
  isShellApprovalTool,
  mergeShellEditedArgs,
} from '@/lib/approval/shellCommandDisplay';
import type { ApprovalToolCall } from '@/store/useApprovalStore';
import type { ApprovalResolveHandler } from './types';
import { useAllowAlwaysChoice } from './useAllowAlwaysChoice';

interface UseShellEditParams {
  approvalId: string;
  toolCalls: ApprovalToolCall[];
  isSubagentApproval: boolean;
  primaryToolName: string;
  comment: string;
  onResolve: ApprovalResolveHandler;
}

/**
 * Editing of a subagent approval that holds exactly one shell call: the call, its editable
 * arguments, the validation of those edits and the decision they lead to. The edits outlive
 * a cancelled edit session, so reopening the editor shows what the user last typed.
 */
export function useShellEdit({
  approvalId,
  toolCalls,
  isSubagentApproval,
  primaryToolName,
  comment,
  onResolve,
}: UseShellEditParams) {
  const t = useTranslations('toolApproval');
  const [isEditing, setIsEditing] = useState(false);
  const [allowAlwaysInEdit, setAllowAlwaysInEdit] = useState(false);
  const {
    scope: allowAlwaysScopeInEdit,
    setScope: setAllowAlwaysScopeInEdit,
    duration: allowAlwaysDurationInEdit,
    setDuration: setAllowAlwaysDurationInEdit,
  } = useAllowAlwaysChoice(approvalId, primaryToolName);
  const [editValidationErrors, setEditValidationErrors] = useState<string[]>([]);
  const [shellEditedArgs, setShellEditedArgs] = useState<Record<string, string>>({});

  const singleShellToolCall = useMemo(() => {
    if (!isSubagentApproval || toolCalls.length !== 1) {
      return null;
    }
    const call = toolCalls[0];
    if (!isShellApprovalTool(call.name) || typeof call.args !== 'object' || call.args === null) {
      return null;
    }
    return call;
  }, [isSubagentApproval, toolCalls]);

  const shellInputEntries = useMemo(() => {
    if (!singleShellToolCall || typeof singleShellToolCall.args !== 'object' || singleShellToolCall.args === null) {
      return [] as Array<[string, unknown]>;
    }
    return getShellEditInputEntries(singleShellToolCall.args as Record<string, unknown>);
  }, [singleShellToolCall]);

  const isSingleStringShellParam = shellInputEntries.length === 1 && typeof shellInputEntries[0][1] === 'string';

  const shellCommand = useMemo(() => {
    if (!singleShellToolCall || typeof singleShellToolCall.args !== 'object' || singleShellToolCall.args === null) {
      return '';
    }
    return extractShellCommand(singleShellToolCall.args as Record<string, unknown>);
  }, [singleShellToolCall]);

  const editedShellCommand = useMemo(
    () => extractShellCommand(shellEditedArgs as Record<string, unknown>),
    [shellEditedArgs],
  );

  useEffect(() => {
    if (!singleShellToolCall || typeof singleShellToolCall.args !== 'object' || singleShellToolCall.args === null) {
      return;
    }
    const initial: Record<string, string> = {};
    for (const [key, val] of shellInputEntries) {
      if (typeof val === 'string') {
        initial[key] = val;
      } else if (val === undefined || val === null) {
        initial[key] = '';
      } else {
        initial[key] = JSON.stringify(val, null, 2);
      }
    }
    setShellEditedArgs(initial);
  }, [shellInputEntries, singleShellToolCall]);

  const handleConfirmShellEdit = useCallback(async () => {
    const parsed: Record<string, unknown> = {};
    const errors: string[] = [];

    for (const [key, val] of Object.entries(shellEditedArgs)) {
      const trimmed = val.trim();
      try {
        parsed[key] = JSON.parse(val);
      } catch {
        if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
          errors.push(key);
        }
        parsed[key] = val;
      }
    }

    if (errors.length > 0) {
      setEditValidationErrors(errors);
      toast.error(t('editValidationError', { fields: errors.join(', ') }));
      return;
    }

    setEditValidationErrors([]);

    const ttlSeconds = allowAlwaysInEdit ? durationToTtlSeconds(allowAlwaysDurationInEdit) : undefined;
    const allowAlwaysValue = !allowAlwaysInEdit
      ? false
      : scopeToAllowAlwaysValue(allowAlwaysScopeInEdit, allowAlwaysDurationInEdit);

    const hasChanges = shellInputEntries.some(([key, original]) => {
      const editedVal = shellEditedArgs[key];
      const originalStr = typeof original === 'string' ? original : JSON.stringify(original, null, 2);
      return editedVal !== originalStr;
    });

    if (hasChanges) {
      const originalArgs =
        typeof singleShellToolCall?.args === 'object' && singleShellToolCall.args !== null
          ? (singleShellToolCall.args as Record<string, unknown>)
          : {};
      await onResolve('edit', comment, undefined, {
        edited_args: mergeShellEditedArgs(originalArgs, parsed),
        allow_always: allowAlwaysValue,
        ttl_seconds: ttlSeconds,
        guidance: comment || undefined,
      });
    } else {
      await onResolve('approve', comment, undefined, {
        allow_always: allowAlwaysValue || undefined,
        ttl_seconds: ttlSeconds,
        guidance: comment || undefined,
      });
    }

    setIsEditing(false);
    setAllowAlwaysInEdit(false);
    setAllowAlwaysScopeInEdit(defaultAllowAlwaysScope(primaryToolName));
    setAllowAlwaysDurationInEdit('session');
  }, [
    allowAlwaysDurationInEdit,
    allowAlwaysInEdit,
    allowAlwaysScopeInEdit,
    comment,
    onResolve,
    primaryToolName,
    setAllowAlwaysDurationInEdit,
    setAllowAlwaysScopeInEdit,
    shellEditedArgs,
    shellInputEntries,
    singleShellToolCall,
    t,
  ]);

  const cancelEditing = () => {
    setIsEditing(false);
    setAllowAlwaysInEdit(false);
    setEditValidationErrors([]);
  };

  return {
    singleShellToolCall,
    shellCommand,
    isEditing,
    startEditing: () => setIsEditing(true),
    /** The props of the shared edit view that this hook owns. */
    editView: {
      editedArgs: shellEditedArgs,
      setEditedArgs: setShellEditedArgs,
      inputEntries: shellInputEntries,
      isSingleStringParam: isSingleStringShellParam,
      editValidationErrors,
      allowAlwaysInEdit,
      setAllowAlwaysInEdit,
      allowAlwaysScopeInEdit,
      setAllowAlwaysScopeInEdit,
      allowAlwaysDurationInEdit,
      setAllowAlwaysDurationInEdit,
      shellCommand: editedShellCommand,
      onConfirm: handleConfirmShellEdit,
      onCancel: cancelEditing,
    },
  };
}
