/**
 * [INPUT]
 * - @/store/chat/useMessageQueueStore::{useMessageQueueStore, selectDrainableHeadId, resolveDrainDelayMs} (POS: 排队消息内存状态源)
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线)
 * - ./turnCapabilityOverrideCore::buildTurnAgentConfigOverride (POS: 单轮能力覆写核心)
 * - ./turnCapabilityTelemetry::{useTurnCapabilityTelemetry, resolveTerminalTelemetry} (POS: 单轮覆写埋点编排)
 * - @/lib/utils/networkResilience::isArchiveRestoreActionInvalidError (POS: 归档恢复动作错误识别)
 *
 * [OUTPUT]
 * - useQueueDrain: sends queued messages one at a time as soon as the agent is idle.
 *
 * [POS]
 * 排队消息的发送循环。单飞（同一时刻只发一条）、编辑中的消息不发、用户 Stop 后暂停、
 * 服务端忙碌按退避重试且次数有限——用尽后转入"卡住"状态等待用户手动重试，绝不丢消息。
 */

import { useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { isArchiveRestoreActionInvalidError } from '@/lib/utils/networkResilience';
import { toast } from '@/lib/utils/toast';
import { resolveDrainDelayMs, selectDrainableHeadId, useMessageQueueStore } from '@/store/chat/useMessageQueueStore';
import useChatStore from '@/store/useChatStore';
import { buildTurnAgentConfigOverride } from './turnCapabilityOverrideCore';
import { resolveTerminalTelemetry, useTurnCapabilityTelemetry } from './turnCapabilityTelemetry';

export function useQueueDrain(chatId: string | null | undefined): void {
  const t = useTranslations('chat');
  const loading = useChatStore((state) => state.loading);
  const telemetry = useTurnCapabilityTelemetry(chatId);
  const queue = useMessageQueueStore((state) => (chatId ? state.queues[chatId] : undefined));
  const headId = selectDrainableHeadId(queue, loading);
  const failedAttempts = queue?.failedAttempts ?? 0;

  const drain = useCallback(
    async (targetChatId: string): Promise<void> => {
      const chat = useChatStore.getState();
      // The chat store serves one chat at a time; a queued message must never be sent into another chat.
      if (chat.chatId !== targetChatId || chat.loading) {
        return;
      }
      const queues = useMessageQueueStore.getState();
      const message = queues.claimHead(targetChatId);
      if (!message) {
        return;
      }

      const selection = message.turnCapabilitySelection ?? null;
      const override = buildTurnAgentConfigOverride(chat.agentConfig, selection) ?? undefined;
      try {
        const dispatched = await chat.sendMessage(
          message.text,
          undefined,
          undefined,
          undefined,
          message.archiveRestoreActions,
          override,
          true,
          resolveTerminalTelemetry('queue_drain', selection, override),
          { files: message.files },
        );
        if (dispatched) {
          telemetry.recordSettled('queue_drain', selection, override);
          queues.releaseClaim(targetChatId, message, 'consumed');
        } else {
          // Refused locally (the reason was already shown to the user): keep the message and wait for them.
          queues.releaseClaim(targetChatId, message, 'blocked');
        }
      } catch (error) {
        if (error instanceof Error && error.name === 'AgentBusyError') {
          if (selection) {
            telemetry.recordBusyRequeued('queue_drain');
          }
          queues.releaseClaim(targetChatId, message, 'busy');
          if (useMessageQueueStore.getState().queues[targetChatId]?.pausedReason === 'stuck') {
            toast.error(t('queue.stuck'));
          }
          return;
        }
        telemetry.recordFailed('queue_drain', selection, override, error);
        if (isArchiveRestoreActionInvalidError(error)) {
          const composer = useChatStore.getState();
          composer.setInputMessage(message.text);
          composer.setFiles(message.files);
          composer.setPendingArchiveRestoreActions(message.archiveRestoreActions ?? []);
        }
        queues.releaseClaim(targetChatId, message, 'consumed');
      }
    },
    [t, telemetry],
  );

  useEffect(() => {
    if (!chatId || headId === null) {
      return;
    }
    const timer = setTimeout(() => {
      void drain(chatId);
    }, resolveDrainDelayMs(failedAttempts));
    return () => clearTimeout(timer);
  }, [chatId, headId, failedAttempts, drain]);
}
