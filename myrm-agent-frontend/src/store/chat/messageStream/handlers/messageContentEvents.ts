/**
 * [POS]
 * Chat SSE event handler slice (messageContentEvents).
 */

import type { StreamCtx, StreamTurn } from '../streamContext';
import * as H from './handlerDeps';

export async function messageContentEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, recievedMessage, state, actions } = ctx;
  if (data.type === H.AgentEventType.REASONING) {
    const reasoningDisplayMode =
      H.useConfigStore.getState().personalSettings?.reasoningDisplayMode ??
      H.useConfigStore.getState().reasoningDisplayMode ??
      'collapsed';
    if (reasoningDisplayMode === 'off') {
      return null;
    }
    if (data.data && data.data.length > 0) {
      const reasoningChunk = H.sanitizeStreamText(data.data as string);

      // 首个思考帧可能早于任何会创建 assistant 消息的事件（routing/status 缺档位时不会建）。
      // 不先建消息，chunk 会被 findAssistantMessageIndex === -1 丢弃，用户只看到静止骨架。
      if (!ctx.added) {
        let ensured = false;
        actions.setMessages((updateState) => {
          ensured =
            H.ensureAssistantStreamMessage(updateState.messages, data.messageId, H.resolveStreamChatId(ctx.state)) !==
            -1;
        });
        if (ensured) {
          ctx.added = true;
        }
      }

      state.scheduler.schedule(() => {
        actions.setMessages((updateState) => {
          const messageIndex = H.findAssistantMessageIndex(updateState.messages, data.messageId);
          if (messageIndex === -1) {
            return;
          }

          if (!updateState.messages[messageIndex].reasoningStartedAt) {
            updateState.messages[messageIndex].reasoningStartedAt = Date.now();
          }

          const currentReasoning = updateState.messages[messageIndex].reasoning || '';
          updateState.messages[messageIndex].reasoning = currentReasoning + reasoningChunk;

          if (!updateState.messageAppeared) {
            updateState.messageAppeared = true;
          }
        });
      }, 0);
    }
  }

  if (data.type === H.AgentEventType.MESSAGE) {
    // LLM已响应，清除Subagent提示计时器
    H.useChatStore.getState().clearSubagentPromptTimer();
    H.useChatStore.getState().setSubagentPromptVisible(false);

    // Finalize reasoning duration when first content chunk arrives
    actions.setMessages((updateState) => {
      const messageIndex = H.findAssistantMessageIndex(updateState.messages, data.messageId);
      if (messageIndex === -1) {
        return;
      }
      const msg = updateState.messages[messageIndex];
      if (msg.reasoningStartedAt && !msg.reasoningDurationMs) {
        msg.reasoningDurationMs = Date.now() - msg.reasoningStartedAt;
      }
    });

    if (data.data && data.data.length > 0) {
      ctx.recievedMessage += H.sanitizeStreamText(data.data as string);

      // 使用自适应防抖调度器，而不是直接调用 requestAnimationFrame
      state.scheduler.schedule(() => {
        actions.setMessages((updateState) => {
          const messageIndex = H.findAssistantMessageIndex(updateState.messages, data.messageId);
          if (messageIndex === -1) {
            return;
          }

          updateState.messages[messageIndex].content = recievedMessage;

          if (!updateState.messageAppeared) {
            updateState.messageAppeared = true;
          }
        });
      }, recievedMessage.length);
    }
  }

  // 处理 artifacts 事件

  return null;
}
