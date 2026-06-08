'use client';

import React, { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { MessageSquare, Clock, AlertTriangle, MousePointerClick, Globe } from 'lucide-react';
import { ApprovalPayload, ApprovalToolCall } from '@/store/useApprovalStore';
import { Button } from '@/components/primitives/button';
import { Textarea } from '@/components/primitives/textarea';
import { LazyMonacoEditor as Editor, LazyMonacoDiffEditor as DiffEditor } from '@/components/features/app-shell/lazy-monaco-editor';
import ShellCommandDisplay from '@/components/features/chat-window/approval/ShellCommandDisplay';
import { extractShellCommand, isShellApprovalTool, parseCommandSpanRisks, parseCommandSpans } from '@/lib/approval/shellCommandDisplay';
import { useTheme } from 'next-themes';
import useApprovalStore from '@/store/useApprovalStore';

interface PolymorphicApprovalCardProps {
  approval: ApprovalPayload;
  onResolve: (
    action: 'approve' | 'reject',
    comment?: string,
    edited_payload?: Record<string, unknown>,
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

export function PolymorphicApprovalCard({ approval, onResolve, isSubmitting }: PolymorphicApprovalCardProps) {
  const t = useTranslations('toolApproval');
  const tNotifications = useTranslations('notifications');
  const router = useRouter();
  const hideDrawer = useApprovalStore((s) => s.hideDrawer);
  const [comment, setComment] = useState('');
  const [editedArgs, setEditedArgs] = useState<string>(() => {
    if (approval.action_type === 'tool_clarification') {
      return JSON.stringify(approval.payload?.content || {}, null, 2);
    }
    return '';
  });
  const { resolvedTheme } = useTheme();

  const isDark = resolvedTheme === 'dark';

  const handleJumpToChat = () => {
    if (!approval.chat_id) return;
    hideDrawer();
    router.push(`/chat/${approval.chat_id}`);
  };

  const renderContent = () => {
    switch (approval.action_type) {
      case 'subagent_approval': {
        const toolCalls: ApprovalToolCall[] = approval.payload?.tool_calls ?? [];
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
                  return (
                    <ShellCommandDisplay
                      key={idx}
                      toolName={call.name}
                      command={command}
                      commandSpans={commandSpans}
                      commandSpanRisks={commandSpanRisks}
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

        return (
          <div className="space-y-4">
            <h4 className="font-medium text-sm text-muted-foreground">{t('skillGrowthPending')}</h4>
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
          </div>
        );
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

      <div className="flex items-center justify-end gap-3 pt-4 border-t">
        <Button variant="outline" onClick={() => onResolve('reject', comment)} disabled={isSubmitting}>
          {t('reject')}
        </Button>
        <Button
          onClick={() => {
            let edited_payload: Record<string, unknown> | undefined = undefined;
            if (approval.action_type === 'tool_clarification') {
              try {
                edited_payload = JSON.parse(editedArgs);
              } catch {
                console.error('Invalid JSON payload');
                // Could add toast here
                return;
              }
            }
            onResolve('approve', comment, edited_payload);
          }}
          disabled={isSubmitting}
        >
          {t('approve')}
        </Button>
      </div>
    </div>
  );
}
