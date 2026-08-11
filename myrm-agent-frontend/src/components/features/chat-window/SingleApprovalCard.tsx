'use client';

import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Globe,
  Terminal,
  Clock,
  Pencil,
  MessageSquareX,
  CheckCircle2,
  ShieldAlert,
  MessageSquarePlus,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Progress } from '@/components/primitives/progress';
import { Textarea } from '@/components/primitives/textarea';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/primitives/collapsible';
import type { ToolApprovalRequest } from '@/store/chat/types';
import type { ToolApprovalResolveExtra } from '@/lib/approval/approvalDecision';
import EditModeView from './approval/EditModeView';
import RejectModeView from './approval/RejectModeView';
import HandoverModeView from './approval/HandoverModeView';
import BrowserSessionView from './approval/BrowserSessionView';
import AllowAlwaysConfirmDialog from './approval/AllowAlwaysConfirmDialog';
import useDesktopInspectorStore, {
  selectScopedDesktopViewData,
} from '@/store/useDesktopInspectorStore';
import useBrowserInspectorStore, {
  selectScopedBrowserViewData,
} from '@/store/useBrowserInspectorStore';
import { resolveVisualApprovalContextForRequest } from '@/lib/approval/visualApprovalContext';
import {
  extractShellCommand,
  getShellEditInputEntries,
  isShellApprovalTool,
  mergeShellEditedArgs,
} from '@/lib/approval/shellCommandDisplay';
import VisualApprovalHighlight from './approval/VisualApprovalHighlight';
import ShellCommandDisplay from './approval/ShellCommandDisplay';
import { type AllowAlwaysScope, defaultAllowAlwaysScope, scopeToAllowAlwaysValue } from '@/lib/approval/allowAlwaysScope';
import {
  classifyApprovalSurface,
  humanizeApprovalTitle,
} from '@/lib/humanize';
import { isSaveSkillApproval } from '@/lib/approval/saveSkillApproval';
import ApprovalScopeNoteLine from '@/components/approval/ApprovalScopeNoteLine';
import SaveSkillApprovalPreview from '@/components/approval/SaveSkillApprovalPreview';
import PtcHintBadges from '@/components/approval/PtcHintBadges';

type DecisionType = 'approve' | 'edit' | 'reject';
type DialogMode = 'default' | 'editing' | 'rejecting';

interface SingleApprovalCardProps {
  request: ToolApprovalRequest;
  onResolve: (
    requestId: string,
    decision: DecisionType,
    extra?: ToolApprovalResolveExtra,
  ) => Promise<void>;
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
  const tHumanize = useTranslations('humanize');
  const [mode, setMode] = useState<DialogMode>('default');
  const [editedArgs, setEditedArgs] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState('');
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  const [showAlwaysAllowConfirm, setShowAlwaysAllowConfirm] = useState(false);
  const [allowAlwaysScope, setAllowAlwaysScope] = useState<AllowAlwaysScope>(() =>
    defaultAllowAlwaysScope(request.toolName),
  );
  const [allowAlwaysInEdit, setAllowAlwaysInEdit] = useState(false);
  const [allowAlwaysScopeInEdit, setAllowAlwaysScopeInEdit] = useState<AllowAlwaysScope>(() =>
    defaultAllowAlwaysScope(request.toolName),
  );
  const [editValidationErrors, setEditValidationErrors] = useState<string[]>([]);
  const [guidance, setGuidance] = useState('');
  const [guidanceOpen, setGuidanceOpen] = useState(false);
  const [grantDirectoryAccess, setGrantDirectoryAccess] = useState(false);

  const desktopViewData = useDesktopInspectorStore((s) =>
    selectScopedDesktopViewData(s.viewData, request.chatId),
  );
  const browserViewData = useBrowserInspectorStore((s) =>
    selectScopedBrowserViewData(s.viewData, request.chatId),
  );

  const visualContext = useMemo(
    () => resolveVisualApprovalContextForRequest(request, desktopViewData, browserViewData),
    [browserViewData, desktopViewData, request],
  );

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

  const editedShellCommand = useMemo(
    () =>
      isShellApprovalTool(request.toolName)
        ? extractShellCommand(editedArgs as Record<string, unknown>)
        : '',
    [editedArgs, request.toolName],
  );

  const isBrowserSession =
    request.toolName === 'browser_manage' &&
    typeof request.toolInput.action === 'string' &&
    ['save_session', 'restore_session', 'list_sessions', 'delete_session'].includes(request.toolInput.action);

  const browserSessionInfo = useMemo(() => {
    if (!isBrowserSession) return null;
    const action = String(request.toolInput.action);
    const domain = String(request.toolInput.value ?? '');
    const actionLabels: Record<string, { zh: string; en: string; desc: { zh: string; en: string } }> = {
      save_session: {
        zh: '保存登录状态',
        en: 'Save Login State',
        desc: {
          zh: '将当前浏览器的 Cookies 和 LocalStorage 加密保存到本地（AES-256-GCM）',
          en: 'Encrypt and save current browser Cookies and LocalStorage locally (AES-256-GCM)',
        },
      },
      restore_session: {
        zh: '恢复登录状态',
        en: 'Restore Login State',
        desc: {
          zh: '从本地加密存储中恢复之前保存的登录状态',
          en: 'Restore previously saved login state from local encrypted storage',
        },
      },
      list_sessions: {
        zh: '列出已保存的会话',
        en: 'List Saved Sessions',
        desc: {
          zh: '查看所有已保存的域名会话列表',
          en: 'View all saved domain sessions',
        },
      },
      delete_session: {
        zh: '删除会话',
        en: 'Delete Session',
        desc: {
          zh: '从本地加密存储中删除指定域名的会话',
          en: 'Delete the session for specified domain from local encrypted storage',
        },
      },
    };
    return {
      action,
      domain,
      label: actionLabels[action]?.zh || action,
      desc: actionLabels[action]?.desc,
    };
  }, [isBrowserSession, request.toolInput]);

  const isSaveSkill = isSaveSkillApproval(request.toolName, request.toolInput);

  const isCompactSurface = compact || classifyApprovalSurface(request.toolName) === 'compact';

  const approvalTitle = useMemo(
    () => humanizeApprovalTitle(request.toolName, request.toolInput, tHumanize),
    [request.toolInput, request.toolName, tHumanize],
  );

  const hideCompactPayload =
    isCompactSurface && !shellCommand && classifyApprovalSurface(request.toolName) === 'compact';

  const permissionTypeLabel =
    request.toolName === 'bash_code_execute_tool' || request.toolName === 'execute_code'
      ? t('permissionTypes.codeInterpreter')
      : request.toolName.startsWith('browser_')
          ? t('permissionTypes.browser')
          : t('permissionTypes.default');

  useEffect(() => {
    const initial: Record<string, string> = {};
    for (const [key, val] of inputEntries) {
      if (typeof val === 'string') {
        initial[key] = val;
      } else if (val === undefined || val === null) {
        initial[key] = '';
      } else {
        initial[key] = JSON.stringify(val, null, 2);
      }
    }
    setEditedArgs(initial);
  }, [inputEntries]);

  useEffect(() => {
    const nextScope = defaultAllowAlwaysScope(request.toolName);
    setAllowAlwaysScope(nextScope);
    setAllowAlwaysScopeInEdit(nextScope);
  }, [request.requestId, request.toolName]);

  useEffect(() => {
    if (mode === 'editing' || mode === 'rejecting') {
      return;
    }

    const update = () => {
      const remaining = Math.max(0, Math.floor((request.expiresAt * 1000 - Date.now()) / 1000));
      setRemainingSeconds(remaining);
    };
    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, [request.expiresAt, mode]);

  const isExpired = remainingSeconds <= 0;
  const isUrgent = remainingSeconds > 0 && remainingSeconds <= 10;
  const progressPercent = Math.max(0, (remainingSeconds / request.timeoutSeconds) * 100);
  const isHandover = request.displayMode === 'handover';

  const guidanceExtra = guidance.trim() ? { guidance: guidance.trim() } : undefined;

  const directoryGrantExtra =
    request.pathGrantEligible && grantDirectoryAccess
      ? {
          grant_directory: true,
          ...(request.pathGrantPath && { grant_directory_path: request.pathGrantPath }),
          grant_directory_writable: request.pathGrantWritable ?? false,
        }
      : undefined;

  const handleApprove = useCallback(
    async () =>
      await onResolve(request.requestId, 'approve', {
        ...guidanceExtra,
        ...directoryGrantExtra,
      }),
    [request.requestId, onResolve, guidanceExtra, directoryGrantExtra],
  );

  const handleAlwaysAllow = useCallback(() => {
    setShowAlwaysAllowConfirm(true);
  }, []);

  const handleAllowDomain = useCallback(
    async () => await onResolve(request.requestId, 'approve', { allow_domain: true }),
    [request.requestId, onResolve],
  );

  const handleConfirmAlwaysAllow = useCallback(async () => {
    setShowAlwaysAllowConfirm(false);
    await onResolve(request.requestId, 'approve', {
      allow_always: scopeToAllowAlwaysValue(allowAlwaysScope),
    });
  }, [allowAlwaysScope, request.requestId, onResolve]);

  const handleConfirmEdit = useCallback(async () => {
    const parsed: Record<string, unknown> = {};
    const errors: string[] = [];

    for (const [key, val] of Object.entries(editedArgs)) {
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

    const hasChanges = inputEntries.some(([key, original]) => {
      const editedVal = editedArgs[key];
      const originalStr = typeof original === 'string' ? original : JSON.stringify(original, null, 2);
      return editedVal !== originalStr;
    });

    const guidanceValue = guidance.trim() || undefined;
    if (hasChanges) {
      const editedArgsPayload = shellCommand
        ? mergeShellEditedArgs(request.toolInput, parsed)
        : parsed;
      await onResolve(request.requestId, 'edit', {
        edited_args: editedArgsPayload,
        allow_always: allowAlwaysValue,
        guidance: guidanceValue,
      });
    } else {
      await onResolve(request.requestId, 'approve', {
        allow_always: allowAlwaysValue || undefined,
        guidance: guidanceValue,
      });
    }
    setAllowAlwaysInEdit(false);
    setAllowAlwaysScopeInEdit(defaultAllowAlwaysScope(request.toolName));
  }, [
    editedArgs,
    inputEntries,
    allowAlwaysInEdit,
    allowAlwaysScopeInEdit,
    request.requestId,
    request.toolInput,
    shellCommand,
    onResolve,
    t,
  ]);

  const handleConfirmReject = useCallback(
    async () => await onResolve(request.requestId, 'reject', { feedback: feedback || undefined }),
    [feedback, request.requestId, onResolve],
  );

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
      {isBrowserSession && browserSessionInfo ? (
        <BrowserSessionView
          action={browserSessionInfo.action}
          domain={browserSessionInfo.domain}
          label={browserSessionInfo.label}
          desc={browserSessionInfo.desc}
        />
      ) : (
        <>
          <div className="flex items-center flex-wrap gap-2">
            <div className="flex flex-col gap-0.5 min-w-0">
              <div className="flex items-center gap-2">
                <Terminal className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="text-sm font-medium truncate">{approvalTitle}</span>
              </div>
              <span
                className="text-xs pl-6 break-words block"
              >
                <ApprovalScopeNoteLine
                  toolName={request.toolName}
                  toolInput={request.toolInput}
                  tHumanize={tHumanize}
                />
              </span>
            </div>
            {request.ptcAnnotations ? (
              <PtcHintBadges annotations={request.ptcAnnotations} t={t} />
            ) : null}
          </div>

          {visualContext && !hideVisualHighlight && (
            <VisualApprovalHighlight visualContext={visualContext} className="mb-2" />
          )}

          {request.smartDenied && (
            <div className="flex items-center gap-2 rounded-md border border-amber-500/50 bg-amber-500/10 px-3 py-2.5 mb-2">
              <ShieldAlert className="h-4 w-4 flex-shrink-0 text-amber-600 dark:text-amber-400" />
              <div className="min-w-0">
                <p className="text-xs font-medium text-amber-700 dark:text-amber-300">
                  {t('smartDenied.title')}
                </p>
                {request.reviewerReason && (
                  <p className="text-xs text-amber-600/80 dark:text-amber-400/80 mt-0.5 break-words">
                    {request.reviewerReason}
                  </p>
                )}
              </div>
            </div>
          )}

          {request.executionIntent && (
            <div className="text-xs text-foreground/90 mb-2 rounded-md border border-border/60 bg-muted/40 px-2.5 py-2">
              <span className="font-medium text-muted-foreground">{t('executionIntent')}:</span>{' '}
              {request.executionIntent}
            </div>
          )}

          {request.reason && (
            <div className="text-xs text-muted-foreground">
              <span className="font-medium">{t('reason')}:</span> {request.reason}
            </div>
          )}

          {shellCommand ? (
            <ShellCommandDisplay
              toolName={request.toolName}
              command={shellCommand}
              commandSpans={request.commandSpans}
              commandSpanRisks={request.commandSpanRisks}
              commandSpanReasons={request.commandSpanReasons}
              plainExplanation={request.plainExplanation}
              workspaceRoot={request.workspaceRoot}
            />
          ) : isSaveSkill ? (
            <SaveSkillApprovalPreview
              toolInput={request.toolInput}
              showFullInstructionsLabel={t('saveSkill.showFullInstructions')}
              showLessLabel={t('saveSkill.showLess')}
              showAllLinesLabel={t('saveSkill.showAllLines')}
              footerText={t('saveSkill.footer')}
            />
          ) : hideCompactPayload ? null : (
            inputEntries.length > 0 && (
              <pre className="max-h-32 overflow-auto rounded-md bg-muted p-2 text-xs font-mono">
                {JSON.stringify(Object.fromEntries(inputEntries), null, 2)}
              </pre>
            )
          )}

          {request.domains && request.domains.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <Globe className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
              <span className="text-xs font-medium text-muted-foreground">{t('domain.label')}:</span>
              {request.domains.map((domain) => (
                <Badge
                  key={domain}
                  variant="outline"
                  className="font-mono text-xs text-emerald-700 dark:text-emerald-400 border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-950/30"
                >
                  {domain}
                </Badge>
              ))}
            </div>
          )}
        </>
      )}

      <div className="space-y-1.5">
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Clock className={`h-3 w-3 ${isUrgent ? 'text-destructive animate-pulse' : ''}`} />
          <span className={isUrgent ? 'text-destructive font-medium' : ''}>
            {isExpired ? t('expired') : t('expiresIn', { seconds: remainingSeconds })}
          </span>
        </div>
        <Progress value={progressPercent} className={`h-1 ${isUrgent ? '[&>div]:bg-destructive' : ''}`} />
      </div>

      <Collapsible open={guidanceOpen} onOpenChange={setGuidanceOpen}>
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {guidanceOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            <MessageSquarePlus className="h-3 w-3" />
            <span>{t('guidance.toggle')}</span>
            {guidance.trim() && !guidanceOpen && (
              <Badge variant="secondary" className="ml-1 text-[10px] h-4 px-1">
                {t('guidance.hasGuidance')}
              </Badge>
            )}
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent className="mt-2">
          <Textarea
            value={guidance}
            onChange={(e) => setGuidance(e.target.value)}
            placeholder={t('guidance.placeholder')}
            className="min-h-[60px] max-h-[120px] text-xs resize-y"
            rows={2}
          />
          <p className="mt-1 text-[10px] text-muted-foreground">{t('guidance.hint')}</p>
        </CollapsibleContent>
      </Collapsible>

      <div className="flex flex-wrap gap-2">
        {request.smartDenied ? (
          <>
            <Button size="sm" variant="outline" onClick={handleApprove} disabled={isLoading || isExpired}>
              <ShieldAlert className="mr-1 h-3.5 w-3.5" />
              {t('smartDenied.overrideOnce')}
            </Button>
            <Button size="sm" variant="destructive" onClick={() => setMode('rejecting')} disabled={isLoading}>
              <MessageSquareX className="mr-1 h-3.5 w-3.5" />
              {t('reject')}
            </Button>
          </>
        ) : (
          <>
            <Button size="sm" onClick={handleApprove} disabled={isLoading || isExpired}>
              <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
              {isSaveSkill ? t('saveSkill.approve') : t('approve')}
            </Button>
            {!isSaveSkill && (
              <Button size="sm" variant="secondary" onClick={() => setMode('editing')} disabled={isLoading || isExpired}>
                <Pencil className="mr-1 h-3.5 w-3.5" />
                {t('edit')}
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setMode('rejecting')} disabled={isLoading}>
              <MessageSquareX className="mr-1 h-3.5 w-3.5" />
              {isSaveSkill ? t('saveSkill.deny') : t('reject')}
            </Button>
            {!isSaveSkill && !request.hideAllowAlways && (
              <Button
                size="sm"
                variant="ghost"
                onClick={handleAlwaysAllow}
                disabled={isLoading || isExpired}
                className="text-xs text-amber-600 hover:text-amber-700"
              >
                {t('allowAlways')}
              </Button>
            )}
            {request.domainApproval && request.domains && request.domains.length > 0 && (
              <Button
                size="sm"
                variant="ghost"
                onClick={handleAllowDomain}
                disabled={isLoading || isExpired}
                className="text-xs text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300"
                title={t('domain.allowDomainDesc')}
              >
                <Globe className="mr-1 h-3.5 w-3.5" />
                {t('domain.allowDomain')}
              </Button>
            )}
            {request.pathGrantEligible && (
              <label className="inline-flex items-center gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={grantDirectoryAccess}
                  onChange={(event) => setGrantDirectoryAccess(event.target.checked)}
                  disabled={isLoading || isExpired}
                  className="h-3.5 w-3.5 rounded border-border accent-primary"
                />
                <span title={t('grantDirectoryDesc')}>{t('grantDirectory')}</span>
              </label>
            )}
          </>
        )}
      </div>

      <AllowAlwaysConfirmDialog
        open={showAlwaysAllowConfirm}
        onOpenChange={setShowAlwaysAllowConfirm}
        allowAlwaysScope={allowAlwaysScope}
        setAllowAlwaysScope={setAllowAlwaysScope}
        permissionTypeLabel={permissionTypeLabel}
        toolName={request.toolName}
        shellCommand={shellCommand}
        onConfirm={handleConfirmAlwaysAllow}
        isLoading={isLoading}
      />
    </div>
  );
}
