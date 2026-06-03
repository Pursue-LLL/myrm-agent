'use client';

import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Globe, Terminal, Clock, Pencil, MessageSquareX, CheckCircle2, ShieldAlert } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Progress } from '@/components/primitives/progress';
import type { ToolApprovalRequest } from '@/store/chat/types';
import EditModeView from './approval/EditModeView';
import RejectModeView from './approval/RejectModeView';
import HandoverModeView from './approval/HandoverModeView';
import BrowserSessionView from './approval/BrowserSessionView';
import AllowAlwaysConfirmDialog from './approval/AllowAlwaysConfirmDialog';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';

type DecisionType = 'approve' | 'edit' | 'reject';
type DialogMode = 'default' | 'editing' | 'rejecting';
type AllowAlwaysScope = 'permission' | 'tool' | 'exact';

interface SingleApprovalCardProps {
  request: ToolApprovalRequest;
  onResolve: (
    requestId: string,
    decision: DecisionType,
    extra?: {
      edited_args?: Record<string, unknown>;
      feedback?: string;
      allow_always?: boolean | { tool?: boolean; args?: boolean };
      allow_domain?: boolean;
    },
  ) => Promise<void>;
  isLoading: boolean;
}

export default function SingleApprovalCard({ request, onResolve, isLoading }: SingleApprovalCardProps) {
  const t = useTranslations('toolApproval');
  const [mode, setMode] = useState<DialogMode>('default');
  const [editedArgs, setEditedArgs] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState('');
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  const [showAlwaysAllowConfirm, setShowAlwaysAllowConfirm] = useState(false);
  const [allowAlwaysScope, setAllowAlwaysScope] = useState<AllowAlwaysScope>('tool');
  const [allowAlwaysInEdit, setAllowAlwaysInEdit] = useState(false);
  const [allowAlwaysScopeInEdit, setAllowAlwaysScopeInEdit] = useState<AllowAlwaysScope>('tool');
  const [editValidationErrors, setEditValidationErrors] = useState<string[]>([]);

  const desktopViewData = useDesktopInspectorStore((s) => s.viewData);
  const browserViewData = useBrowserInspectorStore((s) => s.viewData);

  const visualContext = useMemo(() => {
    const isDesktop = request.toolName.startsWith('desktop_');
    const isBrowser = request.toolName.startsWith('browser_');
    if (!isDesktop && !isBrowser) return null;

    const refStr = request.toolInput.ref || request.toolInput.element_id || request.toolInput.id;
    if (typeof refStr !== 'string') return null;

    const viewData = isDesktop ? desktopViewData : browserViewData;
    if (!viewData || !viewData.screenshotBase64) return null;

    const targetRef = viewData.refs[refStr];
    if (!targetRef || !targetRef.bbox) return null;

    return {
      base64: viewData.screenshotBase64,
      mimeType: viewData.mimeType,
      bbox: {
        x: targetRef.bbox.viewport_x ?? targetRef.bbox.x,
        y: targetRef.bbox.viewport_y ?? targetRef.bbox.y,
        width: targetRef.bbox.width,
        height: targetRef.bbox.height,
      },
      viewportWidth: viewData.viewportWidth,
      viewportHeight: viewData.viewportHeight,
    };
  }, [request.toolName, request.toolInput, desktopViewData, browserViewData]);

  const inputEntries = useMemo(() => Object.entries(request.toolInput).slice(0, 8), [request.toolInput]);

  const isSingleStringParam = inputEntries.length === 1 && typeof inputEntries[0][1] === 'string';

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

  const permissionTypeLabel =
    request.toolName === 'bash_code_execute_tool' || request.toolName === 'execute_code'
      ? t('permissionTypes.codeInterpreter')
      : request.toolName === 'bash_tool'
        ? t('permissionTypes.shellExec')
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

  const handleApprove = useCallback(
    async () => await onResolve(request.requestId, 'approve'),
    [request.requestId, onResolve],
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
    const allowAlwaysValue =
      allowAlwaysScope === 'permission'
        ? true
        : allowAlwaysScope === 'exact'
          ? { tool: true, args: true }
          : { tool: true };
    await onResolve(request.requestId, 'approve', { allow_always: allowAlwaysValue });
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
      : allowAlwaysScopeInEdit === 'permission'
        ? true
        : allowAlwaysScopeInEdit === 'exact'
          ? { tool: true, args: true }
          : { tool: true };

    const hasChanges = inputEntries.some(([key, original]) => {
      const editedVal = editedArgs[key];
      const originalStr = typeof original === 'string' ? original : JSON.stringify(original, null, 2);
      return editedVal !== originalStr;
    });

    if (hasChanges) {
      await onResolve(request.requestId, 'edit', {
        edited_args: parsed,
        allow_always: allowAlwaysValue,
      });
    } else {
      await onResolve(request.requestId, 'approve', {
        allow_always: allowAlwaysValue || undefined,
      });
    }
    setAllowAlwaysInEdit(false);
    setAllowAlwaysScopeInEdit('tool');
  }, [editedArgs, inputEntries, allowAlwaysInEdit, allowAlwaysScopeInEdit, request.requestId, onResolve, t]);

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
        requestId={request.requestId}
        onConfirm={handleConfirmEdit}
        onCancel={() => {
          setMode('default');
          setAllowAlwaysInEdit(false);
          setEditValidationErrors([]);
        }}
        isLoading={isLoading}
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
    <div className="space-y-3 rounded-lg border p-4">
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
            <div className="flex items-center gap-2">
              <Terminal className="h-4 w-4 text-muted-foreground" />
              <Badge variant="secondary" className="font-mono text-xs">
                {request.toolName}
              </Badge>
            </div>
            {request.ptcAnnotations && (
              <div className="flex items-center gap-1.5">
                {request.ptcAnnotations.readOnlyHint && (
                  <Badge
                    variant="outline"
                    className="text-[10px] h-5 px-1.5 bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-400 border-green-200 dark:border-green-800"
                    title="This tool only reads data and does not modify state."
                  >
                    <CheckCircle2 className="w-3 h-3 mr-1" />
                    Read-Only
                  </Badge>
                )}
                {request.ptcAnnotations.destructiveHint && (
                  <Badge
                    variant="outline"
                    className="text-[10px] h-5 px-1.5 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-400 border-red-200 dark:border-red-800"
                    title="This tool makes destructive, irreversible changes."
                  >
                    <ShieldAlert className="w-3 h-3 mr-1" />
                    Destructive
                  </Badge>
                )}
                {request.ptcAnnotations.openWorldHint && (
                  <Badge
                    variant="outline"
                    className="text-[10px] h-5 px-1.5 bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800"
                    title="This tool interacts with external systems or networks."
                  >
                    <Globe className="w-3 h-3 mr-1" />
                    Open World
                  </Badge>
                )}
              </div>
            )}
          </div>

          {visualContext && (
            <div className="relative overflow-hidden rounded-md border bg-black mb-2" style={{ maxHeight: '300px' }}>
              <img
                src={`data:${visualContext.mimeType || 'image/jpeg'};base64,${visualContext.base64}`}
                alt="Target context"
                className="w-full h-auto object-contain opacity-80"
              />
              <div
                className="absolute border-2 border-red-500 bg-red-500/20 shadow-[0_0_0_9999px_rgba(0,0,0,0.6)] transition-all animate-pulse pointer-events-none"
                style={{
                  left: `${(visualContext.bbox.x / visualContext.viewportWidth) * 100}%`,
                  top: `${(visualContext.bbox.y / visualContext.viewportHeight) * 100}%`,
                  width: `${(visualContext.bbox.width / visualContext.viewportWidth) * 100}%`,
                  height: `${(visualContext.bbox.height / visualContext.viewportHeight) * 100}%`,
                }}
              />
            </div>
          )}

          {request.reason && (
            <div className="text-xs text-muted-foreground">
              <span className="font-medium">{t('reason')}:</span> {request.reason}
            </div>
          )}

          {inputEntries.length > 0 && (
            <pre className="max-h-32 overflow-auto rounded-md bg-muted p-2 text-xs font-mono">
              {JSON.stringify(Object.fromEntries(inputEntries), null, 2)}
            </pre>
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

      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={handleApprove} disabled={isLoading || isExpired}>
          <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
          {t('approve')}
        </Button>
        <Button size="sm" variant="secondary" onClick={() => setMode('editing')} disabled={isLoading || isExpired}>
          <Pencil className="mr-1 h-3.5 w-3.5" />
          {t('edit')}
        </Button>
        <Button size="sm" variant="outline" onClick={() => setMode('rejecting')} disabled={isLoading}>
          <MessageSquareX className="mr-1 h-3.5 w-3.5" />
          {t('reject')}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={handleAlwaysAllow}
          disabled={isLoading || isExpired}
          className="text-xs text-amber-600 hover:text-amber-700"
        >
          {t('allowAlways')}
        </Button>
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
      </div>

      <AllowAlwaysConfirmDialog
        open={showAlwaysAllowConfirm}
        onOpenChange={setShowAlwaysAllowConfirm}
        allowAlwaysScope={allowAlwaysScope}
        setAllowAlwaysScope={setAllowAlwaysScope}
        permissionTypeLabel={permissionTypeLabel}
        toolName={request.toolName}
        onConfirm={handleConfirmAlwaysAllow}
        isLoading={isLoading}
      />
    </div>
  );
}
