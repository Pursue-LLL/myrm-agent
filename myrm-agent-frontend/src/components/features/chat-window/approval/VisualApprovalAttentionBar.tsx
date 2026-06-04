'use client';

/**
 * [INPUT]
 * - @/lib/approval/visualApprovalSurface::partitionApprovalQueue (POS: inline vs modal routing)
 * - @/hooks/useToolApprovalResolve (POS: SSE resume for approve/reject)
 * - @/store/useToolApprovalStore (POS: pending HITL queue)
 * - @/store/useChatStore (POS: active chat id filter)
 *
 * [OUTPUT]
 * - VisualApprovalAttentionBar: fixed strip above MessageInput for pending inline visual approvals
 *
 * [POS]
 * Scroll-independent discoverability for browser_/desktop_ HITL cards in desktop Chat.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { AlertTriangle, LocateFixed, MessageSquareX } from 'lucide-react';

import { Button } from '@/components/primitives/button';
import { selectEarliestInlineRequest } from '@/lib/approval/resolveDesktopOverlayTarget';
import { partitionApprovalQueue } from '@/lib/approval/visualApprovalSurface';
import { useToolApprovalResolve } from '@/hooks/useToolApprovalResolve';
import useChatStore from '@/store/useChatStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';

interface VisualApprovalAttentionMessage {
  messageId: string | number;
}

interface VisualApprovalAttentionBarProps {
  messages: VisualApprovalAttentionMessage[];
  onJumpToMessage: (messageIndex: number) => void;
}

function resolveRemainingSeconds(expiresAt: number, nowMs: number): number {
  return Math.max(0, Math.ceil(expiresAt - nowMs / 1000));
}

export default function VisualApprovalAttentionBar({
  messages,
  onJumpToMessage,
}: VisualApprovalAttentionBarProps) {
  const t = useTranslations('toolApproval');
  const chatId = useChatStore((state) => state.chatId);
  const queue = useToolApprovalStore((state) => state.queue);
  const { rejectAll, isLoading } = useToolApprovalResolve();
  const [nowMs, setNowMs] = useState(() => Date.now());

  const inlineRequests = useMemo(() => {
    if (!chatId) {
      return [];
    }

    const chatQueue = queue.filter((request) => request.chatId === chatId);
    return partitionApprovalQueue(chatQueue).inlineRequests;
  }, [chatId, queue]);

  const primaryRequest = useMemo(
    () => selectEarliestInlineRequest(inlineRequests),
    [inlineRequests],
  );

  const remainingSeconds = primaryRequest ? resolveRemainingSeconds(primaryRequest.expiresAt, nowMs) : 0;

  useEffect(() => {
    if (inlineRequests.length === 0) {
      return;
    }

    const timer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [inlineRequests.length]);

  const handleViewApproval = useCallback(() => {
    if (!primaryRequest) {
      return;
    }

    const targetIndex = messages.findIndex(
      (message) => String(message.messageId) === String(primaryRequest.messageId),
    );
    if (targetIndex >= 0) {
      onJumpToMessage(targetIndex);
    }
  }, [messages, onJumpToMessage, primaryRequest]);

  const handleRejectAll = useCallback(() => {
    void rejectAll(inlineRequests);
  }, [inlineRequests, rejectAll]);

  if (inlineRequests.length === 0 || !primaryRequest) {
    return null;
  }

  const summary =
    inlineRequests.length > 1
      ? t('visualApprovalAttentionMultiple', { count: inlineRequests.length })
      : primaryRequest.toolName;

  return (
    <div
      role="alert"
      aria-live="assertive"
      aria-labelledby="visual-approval-attention-title"
      className="rounded-xl border-2 border-amber-500/40 bg-gradient-to-b from-amber-500/10 to-background/95 px-4 py-3 shadow-sm backdrop-blur-sm"
      data-testid="visual-approval-attention-bar"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" />
          <div className="min-w-0 space-y-1">
            <p id="visual-approval-attention-title" className="text-sm font-semibold text-foreground">
              {t('visualApprovalAttentionTitle')}
            </p>
            <p className="truncate text-xs text-muted-foreground">{summary}</p>
            <p className="text-xs font-mono text-muted-foreground">
              {remainingSeconds > 0 ? t('expiresIn', { seconds: remainingSeconds }) : t('expired')}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2 self-end sm:self-auto">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 border-amber-500/30"
            onClick={handleRejectAll}
            disabled={isLoading}
          >
            <MessageSquareX className="mr-1.5 h-3.5 w-3.5" />
            {t('rejectAll')}
          </Button>
          <Button
            type="button"
            size="sm"
            className="h-8 bg-amber-600 text-white hover:bg-amber-600/90 dark:bg-amber-500 dark:hover:bg-amber-500/90"
            onClick={handleViewApproval}
          >
            <LocateFixed className="mr-1.5 h-3.5 w-3.5" />
            {t('visualApprovalAttentionView')}
          </Button>
        </div>
      </div>
    </div>
  );
}
