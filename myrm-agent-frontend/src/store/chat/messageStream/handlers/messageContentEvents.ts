/**
 * [POS]
 * Chat SSE event handler slice (messageContentEvents).
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import * as H from "./handlerDeps";

export async function messageContentEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, recievedMessage, state, actions } = ctx;
  if (data.type === H.AgentEventType.REASONING) {
    if (data.data && data.data.length > 0) {
      const reasoningChunk = H.sanitizeStreamText(data.data as string);

      state.scheduler.schedule(() => {
        actions.setMessages((updateState) => {
          const messageIndex = H.findAssistantMessageIndex(updateState.messages, data.messageId);
          if (messageIndex === -1) return;

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
      if (messageIndex === -1) return;
      const msg = updateState.messages[messageIndex];
      if (msg.reasoningStartedAt && !msg.reasoningDurationMs) {
        msg.reasoningDurationMs = Date.now() - msg.reasoningStartedAt;
      }
    });

    const isClarify =
      typeof data.metadata === 'object' &&
      data.metadata !== null &&
      (data.metadata as Record<string, unknown>).phase === 'clarify';

    const clarifyMeta = isClarify ? (data.metadata as Record<string, unknown>) : undefined;
    const clarificationForm = isClarify ? H.normalizeClarificationForm(clarifyMeta?.form) : undefined;
    let clarifyOptions: string[] | undefined = undefined;
    let clarifyAllowMultiple = false;
    if (isClarify && clarifyMeta) {
      if (Array.isArray(clarifyMeta.options)) {
        clarifyOptions = clarifyMeta.options.filter((item): item is string => typeof item === 'string');
      }
      if (typeof clarifyMeta.allow_multiple === 'boolean') {
        clarifyAllowMultiple = clarifyMeta.allow_multiple;
      }
      if (clarificationForm) {
        const firstQuestion = clarificationForm.questions[0];
        if (firstQuestion?.options && firstQuestion.options.length > 0) {
          clarifyOptions = firstQuestion.options.map((option) => option.label);
        }
        if (typeof firstQuestion?.allowMultiple === 'boolean') {
          clarifyAllowMultiple = firstQuestion.allowMultiple;
        }
      }
    }

    if (data.data && data.data.length > 0) {
      ctx.recievedMessage += H.sanitizeStreamText(data.data as string);

      // 使用自适应防抖调度器，而不是直接调用 requestAnimationFrame
      state.scheduler.schedule(() => {
        actions.setMessages((updateState) => {
          const messageIndex = H.findAssistantMessageIndex(updateState.messages, data.messageId);
          if (messageIndex === -1) return;

          updateState.messages[messageIndex].content = recievedMessage;

          if (isClarify) {
            updateState.messages[messageIndex].clarification = {
              question: recievedMessage,
              answered: false,
              options: clarifyOptions,
              allowMultiple: clarifyAllowMultiple,
              ...(clarificationForm
                ? {
                    title: clarificationForm.title ?? undefined,
                    form: clarificationForm,
                  }
                : {}),
            };
          }

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
