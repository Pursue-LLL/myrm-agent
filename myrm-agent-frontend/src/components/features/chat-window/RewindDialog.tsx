/**
 * Rewind Dialog — choose what to roll back (conversation and/or file changes)
 * and confirm before rewinding to before a user message.
 */

'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Undo2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { rewindToMessage, type RewindResult } from '@/services/chat';
import { ApiError } from '@/lib/api';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { useToast } from '@/hooks/shared/useToast';
import useChatStore from '@/store/useChatStore';
import { stripUserMessageDisplayText, parseExplicitSkillActivation } from '@/lib/utils/messageUtils';

interface RewindDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chatId: string;
  messageId: string;
  messageIndex: number;
}

interface FileChangeInfo {
  path: string;
  operation: string;
  has_original: boolean;
  timestamp: number;
  revertible: boolean;
  skip_reason?: string | null;
}

type RewindScope = 'conversation' | 'both';

interface FileChangeItem {
  path: string;
  operation: string;
  revertible: boolean;
}

interface FilePreview {
  status: 'checking' | 'ready' | 'empty';
  fileCount: number;
  skippedCount: number;
  files: FileChangeItem[];
}

export function RewindDialog({ open, onOpenChange, chatId, messageId, messageIndex }: RewindDialogProps) {
  const { toast } = useToast();
  const t = useTranslations('chat.rewind');
  const [isRewinding, setIsRewinding] = useState(false);
  const [scope, setScope] = useState<RewindScope>('both');
  const [preview, setPreview] = useState<FilePreview>({
    status: 'checking',
    fileCount: 0,
    skippedCount: 0,
    files: [],
  });

  useEffect(() => {
    if (!open) {
      return;
    }

    let cancelled = false;
    setPreview({ status: 'checking', fileCount: 0, skippedCount: 0, files: [] });

    const assistantIds = useChatStore
      .getState()
      .messages.slice(messageIndex)
      .filter((m) => m.role === 'assistant')
      .map((m) => m.messageId);

    if (assistantIds.length === 0) {
      setPreview({ status: 'empty', fileCount: 0, skippedCount: 0, files: [] });
      return;
    }

    (async () => {
      const results = await Promise.all(
        assistantIds.map(async (mid) => {
          try {
            const res = await fetch(`${getBackendUrl()}/api/v1/files/revert/changes/${chatId}/${mid}`, {
              headers: getAuthHeaders(),
            });
            if (!res.ok) {
              return [] as FileChangeInfo[];
            }
            const body = (await res.json()) as unknown;
            return Array.isArray(body) ? (body as FileChangeInfo[]) : [];
          } catch {
            return [] as FileChangeInfo[];
          }
        }),
      );
      if (cancelled) {
        return;
      }

      const filesMap = new Map<string, FileChangeItem>();
      for (const list of results) {
        for (const change of list) {
          if (!filesMap.has(change.path)) {
            filesMap.set(change.path, {
              path: change.path,
              operation: change.operation,
              revertible: change.revertible,
            });
          }
        }
      }
      const allFiles = Array.from(filesMap.values());
      const revertibleCount = allFiles.filter((f) => f.revertible).length;
      const skippedCount = allFiles.filter((f) => !f.revertible).length;

      setPreview({
        status: revertibleCount > 0 ? 'ready' : 'empty',
        fileCount: revertibleCount,
        skippedCount,
        files: allFiles,
      });
    })();

    return () => {
      cancelled = true;
    };
  }, [open, chatId, messageId, messageIndex]);

  const handleRewind = async () => {
    if (useChatStore.getState().loading) {
      toast({
        title: t('failed'),
        description: t('streamingBlocked'),
        variant: 'destructive',
      });
      return;
    }

    setIsRewinding(true);
    try {
      const response = await rewindToMessage(chatId, messageId, scope);
      const envelope = response as { data?: RewindResult };
      const payload = envelope.data ?? (response as RewindResult);
      const composerRaw = typeof payload.composer_text === 'string' ? payload.composer_text : '';
      const activation = parseExplicitSkillActivation(composerRaw);
      const composerText = activation ? activation.instruction : stripUserMessageDisplayText(composerRaw);

      useChatStore.setState((state) => ({
        messages: state.messages.slice(0, messageIndex),
        inputMessage: composerText,
      }));

      const revertedCount = payload.reverted_files?.length ?? 0;
      const notices: string[] = [];
      if (scope === 'both' && revertedCount > 0) {
        notices.push(t('filesRevertedToast', { count: revertedCount }));
      }
      if (payload.goal_paused) {
        notices.push(t('goalPausedNotice'));
      }
      toast({
        title: t('success'),
        description: notices.length > 0 ? notices.join(' ') : t('successDescription'),
      });
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.code === 409) {
        toast({
          title: t('failed'),
          description: t('streamingBlocked'),
          variant: 'destructive',
        });
        return;
      }
      const message = error instanceof Error ? error.message : t('unknownError');
      toast({
        title: t('failed'),
        description: message,
        variant: 'destructive',
      });
    } finally {
      setIsRewinding(false);
    }
  };

  const scopeOptions: Array<{ value: RewindScope; title: string; description: string }> = [
    {
      value: 'conversation',
      title: t('scopeConversation'),
      description: t('scopeConversationDesc'),
    },
    {
      value: 'both',
      title: t('scopeBoth'),
      description: t('scopeBothDesc'),
    },
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Undo2 className="h-5 w-5" />
            {t('title')}
          </DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <p className="text-sm font-medium">{t('scopeTitle')}</p>
          <div className="grid gap-2">
            {scopeOptions.map((option) => {
              const active = scope === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setScope(option.value)}
                  className={`rounded-lg border p-3 text-left transition-colors ${
                    active ? 'border-primary bg-primary/10' : 'border-border hover:bg-muted'
                  }`}
                >
                  <span className="block text-sm font-medium">{option.title}</span>
                  <span className="block text-xs text-muted-foreground">{option.description}</span>
                </button>
              );
            })}
          </div>

          {scope === 'both' && preview.status === 'checking' && (
            <p className="text-sm text-muted-foreground">{t('filesChecking')}</p>
          )}
          {scope === 'both' && preview.status === 'ready' && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">{t('fileRevertSummary', { count: preview.fileCount })}</p>
              {preview.files.length > 0 && (
                <div
                  data-testid="rewind-files-list"
                  className="max-h-36 overflow-y-auto rounded-md border border-border/60 bg-muted/30 p-2 text-xs divide-y divide-border/40"
                >
                  {preview.files.map((file) => {
                    const fileName = file.path.split('/').pop() || file.path;
                    const dirName = file.path.includes('/')
                      ? file.path.substring(0, file.path.lastIndexOf('/'))
                      : '';
                    const opLower = file.operation?.toLowerCase();
                    const isAdded = opLower === 'create' || opLower === 'add';
                    const isDeleted = opLower === 'delete' || opLower === 'remove';

                    const badgeClass = isAdded
                      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
                      : isDeleted
                      ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20'
                      : 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20';

                    const opKey = isAdded
                      ? 'operationAdded'
                      : isDeleted
                      ? 'operationDeleted'
                      : 'operationModified';

                    return (
                      <div
                        key={file.path}
                        className="flex items-center justify-between gap-2 py-1.5 first:pt-0 last:pb-0"
                      >
                        <div className="min-w-0 flex-1 truncate font-mono" title={file.path}>
                          <span className="font-medium text-foreground">{fileName}</span>
                          {dirName && (
                            <span className="ml-1 text-[11px] text-muted-foreground/80 truncate">({dirName})</span>
                          )}
                        </div>
                        <span
                          className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-medium leading-none ${badgeClass}`}
                        >
                          {t(opKey)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
          {scope === 'both' && preview.status === 'empty' && (
            <p className="text-sm text-muted-foreground">{t('noFileSnapshots')}</p>
          )}
          {scope === 'both' && preview.skippedCount > 0 && (
            <p className="text-sm text-muted-foreground">{t('filesSkippedNotice', { count: preview.skippedCount })}</p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isRewinding}>
            {t('cancel')}
          </Button>
          <Button onClick={handleRewind} disabled={isRewinding}>
            {isRewinding ? t('rewinding') : t('confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
