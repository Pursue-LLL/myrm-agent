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

interface FilePreview {
  status: 'checking' | 'ready' | 'empty';
  fileCount: number;
  skippedCount: number;
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
  });

  useEffect(() => {
    if (!open) {
      return;
    }

    let cancelled = false;
    setPreview({ status: 'checking', fileCount: 0, skippedCount: 0 });

    const assistantIds = useChatStore
      .getState()
      .messages.slice(messageIndex)
      .filter((m) => m.role === 'assistant')
      .map((m) => m.messageId);

    if (assistantIds.length === 0) {
      setPreview({ status: 'empty', fileCount: 0, skippedCount: 0 });
      return;
    }

    (async () => {
      const results = await Promise.all(
        assistantIds.map(async (mid) => {
          try {
            const res = await fetch(`/api/v1/files/revert/changes/${chatId}/${mid}`, {
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

      const revertiblePaths = new Set<string>();
      const skippedPaths = new Set<string>();
      for (const list of results) {
        for (const change of list) {
          (change.revertible ? revertiblePaths : skippedPaths).add(change.path);
        }
      }
      setPreview({
        status: revertiblePaths.size > 0 ? 'ready' : 'empty',
        fileCount: revertiblePaths.size,
        skippedCount: skippedPaths.size,
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
            <p className="text-sm text-muted-foreground">{t('fileRevertSummary', { count: preview.fileCount })}</p>
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
