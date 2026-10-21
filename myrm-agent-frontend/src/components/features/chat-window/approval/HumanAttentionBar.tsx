'use client';

/**
 * [INPUT]
 * - @/lib/hitl/humanAttentionSummary::buildHumanAttentionSummary
 * - @/hooks/approval/useToolApprovalResolve (reject modal queue)
 * - @/store/useToolApprovalStore, useDesktopControlApprovalStore, useChatStore
 *
 * [OUTPUT]
 * - HumanAttentionBar: unified pending HITL strip above MessageInput
 *
 * [POS]
 * Aggregates clarify, desktop control gate, and tool/visual approvals without merging SSE payloads.
 */

import { useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { AlertTriangle, LocateFixed } from 'lucide-react';

import { Button } from '@/components/primitives/button';
import { buildHumanAttentionSummary, type HumanAttentionItem } from '@/lib/hitl/humanAttentionSummary';
import { partitionApprovalQueue } from '@/lib/approval/visualApprovalSurface';
import { useToolApprovalResolve } from '@/hooks/approval/useToolApprovalResolve';
import useChatStore from '@/store/useChatStore';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import VisualApprovalAttentionBar from './VisualApprovalAttentionBar';

interface HumanAttentionMessage {
  messageId: string | number;
}

interface HumanAttentionBarProps {
  messages: HumanAttentionMessage[];
  onJumpToMessage: (messageIndex: number) => void;
}

function resolveMessageIndex(messages: HumanAttentionMessage[], messageId: string): number {
  return messages.findIndex((message) => String(message.messageId) === messageId);
}

function kindLabel(item: HumanAttentionItem, t: ReturnType<typeof useTranslations<'toolApproval'>>): string {
  switch (item.kind) {
    case 'clarify':
      return t('humanAttentionKindClarify');
    case 'desktop_control':
      return t('humanAttentionKindDesktopControl');
    case 'visual_approval':
      return t('humanAttentionKindVisual');
    case 'tool_approval':
      return t('humanAttentionKindTool');
    default:
      return item.summary;
  }
}

export default function HumanAttentionBar({ messages, onJumpToMessage }: HumanAttentionBarProps) {
  const t = useTranslations('toolApproval');
  const chatId = useChatStore((state) => state.chatId);
  const queue = useToolApprovalStore((state) => state.queue);
  const desktopPending = useDesktopControlApprovalStore((state) => state.pending);
  const desktopMessageId = useDesktopControlApprovalStore((state) => state.messageId);
  const desktopAppName = useDesktopControlApprovalStore((state) => state.appName);
  const desktopReason = useDesktopControlApprovalStore((state) => state.reason);
  const { rejectAll, isLoading } = useToolApprovalResolve();

  const fullMessages = useChatStore((state) => state.messages);

  const items = useMemo(
    () =>
      buildHumanAttentionSummary({
        chatId,
        messages: fullMessages,
        approvalQueue: queue,
        desktopControlPending: desktopPending,
        desktopControlMessageId: desktopMessageId,
        desktopControlAppName: desktopAppName,
        desktopControlReason: desktopReason,
      }),
    [
      chatId,
      fullMessages,
      queue,
      desktopPending,
      desktopMessageId,
      desktopAppName,
      desktopReason,
    ],
  );

  const primary = items[0] ?? null;

  const visualOnly =
    items.length > 0 && items.every((entry) => entry.kind === 'visual_approval');

  const handleJump = useCallback(() => {
    if (!primary) {
      return;
    }
    const index = resolveMessageIndex(messages, primary.messageId);
    if (index >= 0) {
      onJumpToMessage(index);
    }
  }, [messages, onJumpToMessage, primary]);

  const handleRejectModal = useCallback(() => {
    if (!chatId) {
      return;
    }
    const modalQueue = partitionApprovalQueue(queue.filter((request) => request.chatId === chatId)).modalRequests;
    if (modalQueue.length > 0) {
      void rejectAll(modalQueue);
    }
  }, [chatId, queue, rejectAll]);

  if (items.length === 0) {
    return null;
  }

  if (visualOnly) {
    return <VisualApprovalAttentionBar messages={messages} onJumpToMessage={onJumpToMessage} />;
  }

  const summaryLine =
    items.length === 1
      ? `${kindLabel(primary!, t)} · ${primary!.summary}`
      : t('humanAttentionMultiple', { count: items.length });

  return (
    <div
      role="alert"
      aria-live="assertive"
      aria-labelledby="human-attention-title"
      className="rounded-xl border-2 border-primary/30 bg-gradient-to-b from-primary/10 to-background/95 px-4 py-3 shadow-sm backdrop-blur-sm"
      data-testid="human-attention-bar"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
          <div className="min-w-0 space-y-1">
            <p id="human-attention-title" className="text-sm font-semibold text-foreground">
              {t('humanAttentionTitle')}
            </p>
            <p className="truncate text-xs text-muted-foreground">{summaryLine}</p>
            <p className="text-[11px] text-muted-foreground">{t('humanAttentionEscHint')}</p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2 self-end sm:self-auto">
          {items.some((entry) => entry.kind === 'tool_approval') ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8"
              onClick={handleRejectModal}
              disabled={isLoading}
            >
              {t('rejectAll')}
            </Button>
          ) : null}
          <Button type="button" size="sm" className="h-8" onClick={handleJump}>
            <LocateFixed className="mr-1.5 h-3.5 w-3.5" />
            {t('humanAttentionView')}
          </Button>
        </div>
      </div>
    </div>
  );
}
