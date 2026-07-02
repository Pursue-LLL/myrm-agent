'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { MessageSquare, Clock, AlertTriangle, MousePointerClick, Globe, ChevronDown, ChevronUp, DollarSign, Layers, Pencil } from 'lucide-react';
import { toast } from 'sonner';
import { ApprovalPayload } from '@/store/useApprovalStore';
import { Button } from '@/components/primitives/button';
import { Textarea } from '@/components/primitives/textarea';
import { LazyMonacoEditor as Editor, LazyMonacoDiffEditor as DiffEditor } from '@/components/features/app-shell/lazy-monaco-editor';
import ShellCommandDisplay from '@/components/features/chat-window/approval/ShellCommandDisplay';
import EditModeView from '@/components/features/chat-window/approval/EditModeView';
import AllowAlwaysConfirmDialog from '@/components/features/chat-window/approval/AllowAlwaysConfirmDialog';
import { type AllowAlwaysScope, scopeToAllowAlwaysValue } from '@/lib/approval/allowAlwaysScope';
import type { ToolApprovalResolveExtra } from '@/lib/approval/approvalDecision';
import {
  extractShellCommand,
  getShellEditInputEntries,
  isShellApprovalTool,
  mergeShellEditedArgs,
  parseCommandSpanReasons,
  parseCommandSpanRisks,
  parseCommandSpans,
  parsePlainExplanation,
} from '@/lib/approval/shellCommandDisplay';
import { useTheme } from 'next-themes';
import useApprovalStore from '@/store/useApprovalStore';

type DrawerDecisionAction = 'approve' | 'reject' | 'edit';
type CardDialogMode = 'default' | 'editing';

interface PolymorphicApprovalCardProps {
  approval: ApprovalPayload;
  onResolve: (
    action: DrawerDecisionAction,
    comment?: string,
    edited_payload?: Record<string, unknown>,
    extra?: ToolApprovalResolveExtra,
  ) => Promise<void>;
  isSubmitting: boolean;
}

function formatRemaining(remainingMs: number, t: ReturnType<typeof useTranslations>): string {
  if (remainingMs <= 0) return t('expired');
  const totalSeconds = Math.ceil(remainingMs / 1000);
  if (totalSeconds < 60) return t('expiresIn', { seconds: totalSeconds });
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

function ExpiryCountdown({ expiresAt }: { expiresAt: string }) {
  const t = useTranslations('toolApproval');
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  const expiresAtMs = new Date(expiresAt).getTime();
  if (Number.isNaN(expiresAtMs)) return null;

  const remaining = expiresAtMs - now;
  const isExpired = remaining <= 0;
  const isUrgent = remaining > 0 && remaining < 60_000;

  return (
    <span
      className={
        'inline-flex items-center gap-1 text-xs ' +
        (isExpired ? 'text-destructive' : isUrgent ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground')
      }
      aria-live="polite"
    >
      <Clock className="h-3 w-3" aria-hidden="true" />
      {formatRemaining(remaining, t)}
    </span>
  );
}

function getLanguageFromPath(filePath: string): string {
  if (!filePath) return 'markdown';
  const ext = filePath.split('.').pop()?.toLowerCase();
  switch (ext) {
    case 'js':
    case 'jsx':
      return 'javascript';
    case 'ts':
    case 'tsx':
      return 'typescript';
    case 'py':
      return 'python';
    case 'json':
      return 'json';
    case 'html':
      return 'html';
    case 'css':
      return 'css';
    case 'md':
      return 'markdown';
    case 'sh':
    case 'bash':
      return 'shell';
    case 'yaml':
    case 'yml':
      return 'yaml';
    case 'rs':
      return 'rust';
    case 'go':
      return 'go';
    case 'java':
      return 'java';
    case 'cpp':
    case 'c':
    case 'h':
    case 'hpp':
      return 'cpp';
    default:
      return 'plaintext';
  }
}

function SkillApprovalContent({
  reason,
  content,
  originalContent,
  language,
  isDark,
  label,
  viewChangesLabel,
  hideChangesLabel,
}: {
  reason?: string;
  content?: string;
  originalContent?: string;
  language: string;
  isDark: boolean;
  label: string;
  viewChangesLabel: string;
  hideChangesLabel: string;
}) {
  const [showDiff, setShowDiff] = useState(false);

  return (
    <div className="space-y-3">
      <h4 className="font-medium text-sm text-muted-foreground">{label}</h4>
      {reason && <p className="text-sm text-foreground">{reason}</p>}
      <button
        type="button"
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        onClick={() => setShowDiff(!showDiff)}
      >
        {showDiff ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        {showDiff ? hideChangesLabel : viewChangesLabel}
      </button>
      {showDiff && (
        <div className="rounded-lg border overflow-hidden h-[400px]">
          {originalContent ? (
            <DiffEditor
              height="400px"
              language={language}
              theme={isDark ? 'vs-dark' : 'light'}
              original={String(originalContent)}
              modified={String(content || '')}
              options={{
                readOnly: true,
                minimap: { enabled: false },
                wordWrap: 'on',
              }}
            />
          ) : (
            <Editor
              height="400px"
              language={language}
              theme={isDark ? 'vs-dark' : 'light'}
              value={String(content || '')}
              options={{
                readOnly: true,
                minimap: { enabled: false },
                wordWrap: 'on',
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}

export function PolymorphicApprovalCard({ approval, onResolve, isSubmitting }: PolymorphicApprovalCardProps) {
  const t = useTranslations('toolApproval');
  const tNotifications = useTranslations('notifications');
  const router = useRouter();
  const hideDrawer = useApprovalStore((s) => s.hideDrawer);
  const [comment, setComment] = useState('');
  const [mode, setMode] = useState<CardDialogMode>('default');
  const [showAlwaysAllowConfirm, setShowAlwaysAllowConfirm] = useState(false);
  const [allowAlwaysScope, setAllowAlwaysScope] = useState<AllowAlwaysScope>('tool');
  const [allowAlwaysInEdit, setAllowAlwaysInEdit] = useState(false);
  const [allowAlwaysScopeInEdit, setAllowAlwaysScopeInEdit] = useState<AllowAlwaysScope>('tool');
  const [editValidationErrors, setEditValidationErrors] = useState<string[]>([]);
  const [shellEditedArgs, setShellEditedArgs] = useState<Record<string, string>>({});
  const [editedArgs, setEditedArgs] = useState<string>(() => {
    if (approval.action_type === 'tool_clarification') {
      return JSON.stringify(approval.payload?.content || {}, null, 2);
    }
    return '';
  });
  const { resolvedTheme } = useTheme();

  const isDark = resolvedTheme === 'dark';
  const isSubagentApproval = approval.action_type === 'subagent_approval';
  const toolCalls = useMemo(
    () => approval.payload?.tool_calls ?? [],
    [approval.payload?.tool_calls],
  );
  const primaryToolName = toolCalls[0]?.name ?? 'unknown';
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

  const isSingleStringShellParam =
    shellInputEntries.length === 1 && typeof shellInputEntries[0][1] === 'string';

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

  const permissionTypeLabel = useMemo(() => {
    if (primaryToolName === 'bash_code_execute_tool' || primaryToolName === 'execute_code') {
      return t('permissionTypes.codeInterpreter');
    }
    if (primaryToolName === 'bash_code_execute_tool') {
      return t('permissionTypes.shellExec');
    }
    if (primaryToolName.startsWith('browser_')) {
      return t('permissionTypes.browser');
    }
    return t('permissionTypes.default');
  }, [primaryToolName, t]);

  const handleConfirmAlwaysAllow = useCallback(async () => {
    setShowAlwaysAllowConfirm(false);
    await onResolve('approve', comment, undefined, {
      allow_always: scopeToAllowAlwaysValue(allowAlwaysScope),
      feedback: comment || undefined,
    });
  }, [allowAlwaysScope, comment, onResolve]);

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

    const allowAlwaysValue = !allowAlwaysInEdit
      ? false
      : scopeToAllowAlwaysValue(allowAlwaysScopeInEdit);

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
        feedback: comment || undefined,
      });
    } else {
      await onResolve('approve', comment, undefined, {
        allow_always: allowAlwaysValue || undefined,
        feedback: comment || undefined,
      });
    }

    setMode('default');
    setAllowAlwaysInEdit(false);
    setAllowAlwaysScopeInEdit('tool');
  }, [
    allowAlwaysInEdit,
    allowAlwaysScopeInEdit,
    comment,
    onResolve,
    shellEditedArgs,
    shellInputEntries,
    singleShellToolCall,
    t,
  ]);

  const handleJumpToChat = () => {
    if (!approval.chat_id) return;
    hideDrawer();
    router.push(`/chat/${approval.chat_id}`);
  };

  const renderContent = () => {
    switch (approval.action_type) {
      case 'subagent_approval': {
        const payloadRecord = approval.payload ?? {};
        const workspaceRoot =
          typeof payloadRecord.workspaceRoot === 'string'
            ? payloadRecord.workspaceRoot
            : typeof (payloadRecord.extensions as { workspaceRoot?: string } | undefined)?.workspaceRoot ===
                'string'
              ? (payloadRecord.extensions as { workspaceRoot: string }).workspaceRoot
              : undefined;
        return (
          <div className="space-y-4">
            <h4 className="font-medium text-sm text-muted-foreground">{t('subagentApprovalRequired')}</h4>
            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {toolCalls.map((call, idx: number) => {
                // Special rendering for file_write tool to show DiffEditor
                if (call.name === 'file_write' && typeof call.args === 'object' && call.args !== null) {
                  const args = call.args as Record<string, any>;
                  const content = args.content || args.file_content || args.text || '';
                  const filePath = args.path || args.file_path || '';
                  const language = getLanguageFromPath(filePath);
                  // We don't have original content here easily, but we can show the new content in a nice editor
                  // If we had original_content in args we could use DiffEditor. For now, just show the new content nicely.
                  return (
                    <div key={idx} className="rounded-lg border overflow-hidden">
                      <div className="bg-muted px-3 py-2 border-b font-mono text-xs text-primary flex items-center justify-between">
                        <span>{call.name}</span>
                        <span className="text-muted-foreground truncate ml-2 max-w-[200px]" title={filePath}>{filePath}</span>
                      </div>
                      <div className="h-[300px]">
                        <Editor
                          height="100%"
                          language={language}
                          theme={isDark ? 'vs-dark' : 'light'}
                          value={String(content)}
                          options={{
                            readOnly: true,
                            minimap: { enabled: false },
                            wordWrap: 'on',
                          }}
                        />
                      </div>
                    </div>
                  );
                }
                
                // Shell / code execution tools
                if (isShellApprovalTool(call.name) && typeof call.args === 'object' && call.args !== null) {
                  const args = call.args as Record<string, unknown>;
                  const command = extractShellCommand(args);
                  const commandSpans = parseCommandSpans(
                    args.command_spans ?? args.commandSpans,
                    command.length,
                  );
                  const commandSpanRisks = commandSpans
                    ? parseCommandSpanRisks(
                        args.command_span_risks ?? args.commandSpanRisks,
                        commandSpans.length,
                      )
                    : undefined;
                  const commandSpanReasons = commandSpans
                    ? parseCommandSpanReasons(
                        args.command_span_reasons ?? args.commandSpanReasons,
                        commandSpans.length,
                      )
                    : undefined;
                  const plainExplanation = parsePlainExplanation(
                    args.plain_explanation ?? args.plainExplanation,
                  );
                  return (
                    <ShellCommandDisplay
                      key={idx}
                      toolName={call.name}
                      command={command}
                      commandSpans={commandSpans}
                      commandSpanRisks={commandSpanRisks}
                      commandSpanReasons={commandSpanReasons}
                      plainExplanation={plainExplanation}
                      workspaceRoot={workspaceRoot}
                    />
                  );
                }

                // Fallback for other tools
                return (
                  <div key={idx} className="rounded-lg border p-4 bg-muted/50">
                    <div className="font-medium font-mono text-sm mb-2 text-primary">{call.name}</div>
                    <pre className="text-xs overflow-x-auto text-muted-foreground whitespace-pre-wrap break-all">
                      {JSON.stringify(call.args, null, 2)}
                    </pre>
                  </div>
                );
              })}
            </div>
          </div>
        );
      }
      case 'skill_draft':
      case 'skill_patch': {
        const content = approval.payload?.content || approval.payload?.patch_content;
        const originalContent = approval.payload?.original_content;
        const language = 'markdown';

        return <SkillApprovalContent
          reason={approval.reason}
          content={content}
          originalContent={originalContent}
          language={language}
          isDark={isDark}
          label={t('skillGrowthPending')}
          viewChangesLabel={t('viewChanges')}
          hideChangesLabel={t('hideChanges')}
        />;
      }
      case 'tool_clarification': {
        const errorMsg = approval.reason || 'Tool execution failed';

        return (
          <div className="space-y-4">
            <h4 className="font-medium text-sm text-red-500">
              {t('clarificationRequired') || 'Error Clarification Required'}
            </h4>
            <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive whitespace-pre-wrap">
              {errorMsg}
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">
                {t('fixParameters') || 'Fix Parameters (JSON)'}
              </label>
              <div className="rounded-lg border overflow-hidden h-[200px]">
                <Editor
                  height="200px"
                  language="json"
                  theme={isDark ? 'vs-dark' : 'light'}
                  value={editedArgs}
                  onChange={(val) => setEditedArgs(val || '')}
                  options={{
                    minimap: { enabled: false },
                    wordWrap: 'on',
                  }}
                />
              </div>
            </div>
          </div>
        );
      }
      case 'semantic_memory':
        return (
          <div className="space-y-4">
            <h4 className="font-medium text-sm text-muted-foreground">{t('memoryUpdate')}</h4>
            <div className="rounded-lg bg-muted p-4 font-mono text-sm whitespace-pre-wrap overflow-x-auto">
              {approval.payload?.content || approval.payload?.patch_content || t('noContent')}
            </div>
          </div>
        );
      case 'batch_cost_approval': {
        const taskCount = (approval.payload?.task_count as number) || 0;
        const estimatedCost = (approval.payload?.estimated_cost_usd as number) || 0;
        const remainingBudget = approval.payload?.remaining_budget_usd as number | undefined;
        const costStatus = (approval.payload?.cost_status as string) || '';
        const isRace = Boolean(approval.payload?.race);
        const isTournament = Boolean(approval.payload?.tournament);
        const taskSummaries = (approval.payload?.tasks as Array<{ agent_type: string; objective: string }>) || [];

        const modeLabel = isTournament
          ? t('batchCostTournament')
          : isRace
            ? t('batchCostRace')
            : t('batchCostParallel');

        return (
          <div className="space-y-4">
            <div className="flex items-center gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 px-4 py-3">
              <DollarSign className="h-5 w-5 flex-shrink-0 text-amber-600 dark:text-amber-400" />
              <div>
                <h4 className="font-semibold text-sm text-amber-700 dark:text-amber-300">
                  {t('batchCostTitle')}
                </h4>
                <p className="text-xs text-amber-600/80 dark:text-amber-400/80 mt-0.5">
                  {t('batchCostDescription')}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg border bg-muted/50 p-3 text-center">
                <div className="text-2xl font-bold text-foreground">
                  ${estimatedCost.toFixed(2)}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {t('batchCostEstimated')}
                </div>
              </div>
              <div className="rounded-lg border bg-muted/50 p-3 text-center">
                <div className="text-2xl font-bold text-foreground">
                  {taskCount}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {t('batchCostTaskCount')}
                </div>
              </div>
            </div>

            {remainingBudget != null && (
              <div className="flex items-center justify-between rounded-lg border bg-muted/30 px-3 py-2 text-sm">
                <span className="text-muted-foreground">{t('batchCostRemaining')}</span>
                <span className="font-mono font-medium">${remainingBudget.toFixed(2)}</span>
              </div>
            )}

            <div className="flex items-center gap-2 text-xs text-muted-foreground px-1">
              <Layers className="h-3.5 w-3.5 flex-shrink-0" />
              <span>{modeLabel}</span>
              {costStatus && costStatus !== 'unknown' && (
                <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-[10px]">{costStatus}</span>
              )}
            </div>

            {taskSummaries.length > 0 && (
              <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
                {taskSummaries.map((task, idx) => (
                  <div key={idx} className="rounded-lg border p-2.5 bg-muted/30">
                    <div className="font-mono text-xs text-primary">{task.agent_type}</div>
                    <div className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{task.objective}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      }
      case 'high_risk_dom_action': {
        const element = approval.payload?.element as { role?: string; name?: string; ref?: string } | undefined;
        const pageUrl = (approval.payload?.page_url as string) || '';
        const toolInput = approval.payload?.tool_input as { action?: string; ref?: string; text?: string } | undefined;
        const reason = approval.reason || (approval.payload?.reason as string) || '';

        return (
          <div className="space-y-4">
            <div className="flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3">
              <AlertTriangle className="h-5 w-5 flex-shrink-0 text-destructive" />
              <div>
                <h4 className="font-semibold text-sm text-destructive">
                  {t('highRiskDomAction')}
                </h4>
                <p className="text-xs text-destructive/80 mt-0.5">{reason}</p>
              </div>
            </div>

            <div className="space-y-3">
              {element && (
                <div className="rounded-lg border bg-muted/50 p-3">
                  <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mb-2">
                    <MousePointerClick className="h-3.5 w-3.5" />
                    {t('targetElement')}
                  </div>
                  <div className="flex flex-wrap gap-2 text-sm">
                    <span className="inline-flex items-center rounded-md bg-primary/10 px-2 py-1 text-xs font-mono font-medium text-primary">
                      {element.role}
                    </span>
                    <span className="font-medium text-foreground">&quot;{element.name}&quot;</span>
                    <span className="text-muted-foreground text-xs">ref: {element.ref}</span>
                  </div>
                </div>
              )}

              {toolInput && (
                <div className="rounded-lg border bg-muted/50 p-3">
                  <div className="text-xs font-medium text-muted-foreground mb-2">
                    {t('action')}
                  </div>
                  <div className="font-mono text-sm">
                    {toolInput.action}({toolInput.ref}{toolInput.text ? `, "${toolInput.text}"` : ''})
                  </div>
                </div>
              )}

              {pageUrl && (
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground px-1">
                  <Globe className="h-3 w-3 flex-shrink-0" />
                  <span className="truncate" title={pageUrl}>{pageUrl}</span>
                </div>
              )}
            </div>
          </div>
        );
      }
      case 'deploy_approval': {
        const artifactName = approval.payload?.artifact_name ?? approval.payload?.artifact_id ?? '';
        const deployMessage = approval.payload?.message ?? approval.reason ?? '';
        return (
          <div className="space-y-4">
            <div className="flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3">
              <Globe className="h-5 w-5 flex-shrink-0 text-amber-600 dark:text-amber-400" />
              <div>
                <h4 className="font-semibold text-sm">{t('deployApprovalTitle')}</h4>
                <p className="text-xs text-muted-foreground mt-0.5">{deployMessage}</p>
              </div>
            </div>
            {artifactName ? (
              <div className="rounded-lg border bg-muted/50 p-3 text-sm">
                <span className="text-muted-foreground">{t('deployApprovalArtifact')}: </span>
                <span className="font-medium">{artifactName}</span>
              </div>
            ) : null}
            <p className="text-xs text-muted-foreground">{t('deployApprovalHint')}</p>
          </div>
        );
      }
      default:
        return (
          <div className="space-y-4">
            <h4 className="font-medium text-sm text-muted-foreground">{t('payloadData')}</h4>
            <div className="rounded-lg bg-muted p-4 font-mono text-sm whitespace-pre-wrap overflow-x-auto">
              {JSON.stringify(approval.payload, null, 2)}
            </div>
          </div>
        );
    }
  };

  const hasMeta = Boolean(approval.chat_id) || Boolean(approval.expires_at);

  if (mode === 'editing' && singleShellToolCall) {
    return (
      <div className="space-y-6" data-subagent-task-id={approval.payload?.subagent_task_id || approval.subagent_task_id}>
        <EditModeView
          editedArgs={shellEditedArgs}
          setEditedArgs={setShellEditedArgs}
          inputEntries={shellInputEntries}
          isSingleStringParam={isSingleStringShellParam}
          editValidationErrors={editValidationErrors}
          allowAlwaysInEdit={allowAlwaysInEdit}
          setAllowAlwaysInEdit={setAllowAlwaysInEdit}
          allowAlwaysScopeInEdit={allowAlwaysScopeInEdit}
          setAllowAlwaysScopeInEdit={setAllowAlwaysScopeInEdit}
          permissionTypeLabel={permissionTypeLabel}
          toolName={singleShellToolCall.name}
          requestId={approval.approval_id}
          onConfirm={handleConfirmShellEdit}
          onCancel={() => {
            setMode('default');
            setAllowAlwaysInEdit(false);
            setEditValidationErrors([]);
          }}
          isLoading={isSubmitting}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-subagent-task-id={approval.payload?.subagent_task_id || approval.subagent_task_id}>
      {hasMeta && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/30 px-3 py-2">
          <div className="flex items-center gap-2 min-w-0">
            {approval.chat_id && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 gap-1 px-2 text-xs"
                onClick={handleJumpToChat}
                aria-label={tNotifications('jumpToChatAria')}
              >
                <MessageSquare className="h-3 w-3" aria-hidden="true" />
                <span>{tNotifications('jumpToChat')}</span>
              </Button>
            )}
          </div>
          {approval.expires_at && <ExpiryCountdown expiresAt={approval.expires_at} />}
        </div>
      )}

      {renderContent()}

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

      <div className="flex flex-wrap items-center justify-end gap-3 pt-4 border-t">
        <Button variant="outline" onClick={() => onResolve('reject', comment, undefined, { feedback: comment || undefined })} disabled={isSubmitting}>
          {t('reject')}
        </Button>
        {singleShellToolCall && approval.action_type !== 'deploy_approval' && (
          <Button variant="secondary" onClick={() => setMode('editing')} disabled={isSubmitting}>
            <Pencil className="mr-1 h-3.5 w-3.5" />
            {t('edit')}
          </Button>
        )}
        {isSubagentApproval && (
          <Button
            variant="ghost"
            onClick={() => setShowAlwaysAllowConfirm(true)}
            disabled={isSubmitting}
            className="text-xs text-amber-600 hover:text-amber-700"
          >
            {t('allowAlways')}
          </Button>
        )}
        <Button
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
            onResolve('approve', comment, edited_payload, { feedback: comment || undefined });
          }}
          disabled={isSubmitting}
        >
          {t('approve')}
        </Button>
      </div>

      {isSubagentApproval && (
        <AllowAlwaysConfirmDialog
          open={showAlwaysAllowConfirm}
          onOpenChange={setShowAlwaysAllowConfirm}
          allowAlwaysScope={allowAlwaysScope}
          setAllowAlwaysScope={setAllowAlwaysScope}
          permissionTypeLabel={permissionTypeLabel}
          toolName={primaryToolName}
          onConfirm={handleConfirmAlwaysAllow}
          isLoading={isSubmitting}
        />
      )}
    </div>
  );
}
