/**
 * [INPUT]
 * @/store/useChatStore (POS: Chat state store and message state façade)
 * @/store/chat/goals/usePlanStore::usePlanStore (POS: Goal plan state refreshed after a regenerate)
 * @/services/chat::{regenerateLastTurn,cancelAgentRequest} (POS: Chat turn control API)
 * @/services/wiki/evidenceMetrics::recordQualityOutcomeNegative (POS: Quality signal of knowledge-base evidence)
 *
 * [OUTPUT]
 * useAssistantMessageActions: The regenerate and cancel handlers of one assistant message.
 *
 * [POS]
 * Turn-control side effects of an assistant message: asking the server to redo the latest turn and re-sending its
 * query, and cancelling a running request together with the waiting step it left in the transcript.
 */

import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import { usePlanStore } from '@/store/chat/goals/usePlanStore';
import { removeWaitingForTurnStep } from '@/store/chat/messageUtils';
import { stripDatetimeTag } from '@/lib/utils/messageUtils';
import { cancelAgentRequest, regenerateLastTurn } from '@/services/chat';
import { recordQualityOutcomeNegative } from '@/services/wiki/evidenceMetrics';

export function useAssistantMessageActions({
  message,
  chatId,
  hasKbEvidence,
}: {
  message: Message;
  chatId: string | undefined;
  /** The answer cites knowledge-base evidence, so replacing it counts as a negative quality outcome. */
  hasKbEvidence: boolean;
}): { handleRegenerate: (instruction?: string) => Promise<boolean>; handleCancel: () => Promise<void> } {
  const sendMessage = useChatStore((state) => state.sendMessage);

  // Resolves whether the regeneration went through, so the menu keeps a custom instruction that was refused.
  const handleRegenerate = async (instruction?: string): Promise<boolean> => {
    if (!chatId) {
      return false;
    }

    try {
      const result = await regenerateLastTurn(chatId, instruction);

      if (result.success && result.query) {
        useChatStore.setState((state) => ({
          messages: state.messages.filter((m) => m.role !== 'assistant' || m.messageId !== message.messageId),
          regenerateSiblingGroupId: result.sibling_group_id,
          regenerateInstruction: instruction,
        }));
        if (hasKbEvidence) {
          recordQualityOutcomeNegative('chat', 1, `chat:${message.messageId}`);
        }

        void usePlanStore.getState().fetchPlan(chatId);

        const cleanQuery = stripDatetimeTag(result.query);
        return await sendMessage(cleanQuery);
      }
      return false;
    } catch (error) {
      console.error('Regenerate failed:', error);
      return false;
    } finally {
      useChatStore.setState({ regenerateSiblingGroupId: undefined, regenerateInstruction: undefined });
    }
  };

  // 取消：调用后端 API 取消正在运行的 Agent 请求
  const handleCancel = async () => {
    try {
      const abortController = useChatStore.getState().abortController;
      await cancelAgentRequest(message.messageId);
      abortController?.abort(); // 关闭 SSE 连接
      // 锁等待期间取消：pump 可能还没走到 waiting_for_turn_clear 就退出了，
      // 前端残留的等待进度步骤在此同步清除，避免 UI 残留卡死。
      useChatStore.getState().setMessages((state) => {
        state.messages = removeWaitingForTurnStep(state.messages, message.messageId);
      });
    } catch (error) {
      console.error('Cancel failed:', error);
    }
  };

  return { handleRegenerate, handleCancel };
}
