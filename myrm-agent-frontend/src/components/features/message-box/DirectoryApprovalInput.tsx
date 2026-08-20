'use client';

/**
 * [INPUT]
 * - @/store/useChatStore::sendMessage (POS: chat SSE resume 发送)
 * - @/lib/tauri::isTauriEnvironment (POS: 桌面原生 picker 分流)
 * - @/lib/sessionAccessRefresh::refreshSessionAccessRoots (POS: grant 后 FE store 与 DB 对齐)
 * - ./DirectoryBrowsePopover (POS: Web 目录浏览 Popover)
 *
 * [OUTPUT]
 * - DirectoryApprovalInput: 目录权限动态提权与 HITL 审批 UI 卡片
 *
 * [POS]
 * Chat 内嵌目录授权卡片；grant/deny 经 LangGraph interrupt resume 回传 server。
 */

import React, { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { FolderOpen } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/primitives/button';
import { isTauriEnvironment } from '@/lib/tauri';
import useChatStore from '@/store/useChatStore';
import { refreshSessionAccessRoots } from '@/lib/sessionAccessRefresh';

import DirectoryBrowsePopover, { rememberDirectoryGrantPath } from './DirectoryBrowsePopover';

interface DirectoryRequestPayload {
  reason?: string;
  path?: string;
  writable?: boolean;
}

interface DirectoryApprovalInputProps {
  messageId: string;
  answered: boolean;
  isResumeMode?: boolean;
  request?: DirectoryRequestPayload;
  onAnswered?: () => void;
}

export default function DirectoryApprovalInput({
  messageId,
  answered,
  isResumeMode = true,
  request,
  onAnswered,
}: DirectoryApprovalInputProps) {
  const t = useTranslations('chat.directoryRequest');
  const sendMessage = useChatStore((state) => state.sendMessage);
  const chatId = useChatStore((state) => state.chatId);
  const [path, setPath] = useState(request?.path ?? '');
  const [writable, setWritable] = useState(Boolean(request?.writable));
  const [submitting, setSubmitting] = useState(false);
  const [browseOpen, setBrowseOpen] = useState(false);

  const markAnswered = () => {
    onAnswered?.();
  };

  const handleTauriPick = useCallback(async () => {
    if (submitting) {return;}
    try {
      const { open: openDialog } = await import('@tauri-apps/plugin-dialog');
      const selected = await openDialog({
        directory: true,
        multiple: false,
        title: t('chooseFolder'),
        defaultPath: path.trim() || undefined,
      });
      if (!selected) {return;}
      const dir = typeof selected === 'string' ? selected : selected[0];
      rememberDirectoryGrantPath(dir);
      setPath(dir);
    } catch (error) {
      console.error('Failed to open native folder picker:', error);
      toast.error(t('browseFailed'));
    }
  }, [path, submitting, t]);

  const handleBrowseClick = useCallback(() => {
    if (submitting) {return;}
    if (isTauriEnvironment()) {
      void handleTauriPick();
      return;
    }
    setBrowseOpen(true);
  }, [handleTauriPick, submitting]);

  const handleGrant = async () => {
    if (submitting) {return;}
    const trimmed = path.trim();
    if (!trimmed) {
      toast.error(t('pathRequired'));
      return;
    }
    setSubmitting(true);
    try {
      const resumeValue = {
        granted: true,
        path: trimmed,
        writable,
      };
      if (isResumeMode) {
        await sendMessage('', messageId, undefined, resumeValue);
      }
      if (chatId) {
        await refreshSessionAccessRoots(chatId, {
          optimistic: { path: trimmed, writable, source: 'hitl_grant' },
        });
      }
      markAnswered();
    } catch (error) {
      console.error('Failed to grant directory access:', error);
      toast.error(t('submitFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeny = async () => {
    if (submitting) {return;}
    setSubmitting(true);
    try {
      const resumeValue = { granted: false };
      if (isResumeMode) {
        await sendMessage('', messageId, undefined, resumeValue);
      }
      markAnswered();
    } catch (error) {
      console.error('Failed to deny directory access:', error);
      toast.error(t('submitFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  if (answered) {
    return (
      <div className="mt-3 rounded-2xl border border-emerald-500/30 bg-emerald-500/5 px-3 py-2.5 text-sm sm:mt-4 sm:px-4 sm:py-3">
        <span className="font-medium text-emerald-700 dark:text-emerald-300">{t('answered')}</span>
      </div>
    );
  }

  return (
    <div className="mt-3 space-y-3 rounded-2xl border border-border/70 bg-card/60 p-3 sm:mt-4 sm:p-4">
      <div>
        <p className="text-sm font-medium text-foreground">{t('title')}</p>
        {request?.reason ? (
          <p className="mt-1 text-sm text-muted-foreground">{request.reason}</p>
        ) : null}
      </div>
      <div className="space-y-2">
        <label className="text-xs font-medium text-muted-foreground">{t('pathLabel')}</label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            type="text"
            value={path}
            onChange={(event) => setPath(event.target.value)}
            placeholder={t('pathPlaceholder')}
            className="w-full flex-1 rounded-xl border border-border/70 bg-background px-3 py-2 text-sm outline-none ring-primary/30 focus:ring-2"
          />
          {isTauriEnvironment() ? (
            <Button
              type="button"
              variant="outline"
              className="shrink-0 rounded-xl"
              disabled={submitting}
              onClick={handleBrowseClick}
            >
              <FolderOpen className="mr-1.5 h-4 w-4" />
              {t('chooseFolder')}
            </Button>
          ) : (
            <DirectoryBrowsePopover
              open={browseOpen}
              onOpenChange={setBrowseOpen}
              seedPath={path.trim()}
              onSelect={setPath}
              disabled={submitting}
              trigger={
                <Button type="button" variant="outline" className="shrink-0 rounded-xl" disabled={submitting}>
                  <FolderOpen className="mr-1.5 h-4 w-4" />
                  {t('chooseFolder')}
                </Button>
              }
            />
          )}
        </div>
      </div>
      <label className="inline-flex items-center gap-2 text-sm text-muted-foreground">
        <input
          type="checkbox"
          checked={writable}
          onChange={(event) => setWritable(event.target.checked)}
          className="h-4 w-4 rounded border-border accent-primary"
        />
        {t('writableLabel')}
      </label>
      <div className="flex flex-col-reverse gap-2 border-t border-border/50 pt-3 sm:flex-row sm:justify-end">
        <button
          type="button"
          onClick={handleDeny}
          disabled={submitting}
          className="inline-flex w-full items-center justify-center rounded-full border border-border/70 px-4 py-2.5 text-sm text-muted-foreground hover:bg-accent/60 disabled:opacity-50 sm:w-auto"
        >
          {t('deny')}
        </button>
        <button
          type="button"
          onClick={handleGrant}
          disabled={submitting}
          className="inline-flex w-full items-center justify-center rounded-full bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 sm:w-auto"
        >
          {t('grant')}
        </button>
      </div>
    </div>
  );
}
