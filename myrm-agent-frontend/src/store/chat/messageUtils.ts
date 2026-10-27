/**
 * [POS]
 * chat store 消息工具函数集：assistant 消息查找/占位创建、restart 协议草稿清空
 * （`clearAssistantDraft` / `discardStreamedDraft`）、UI artifact 定位与建议生成
 * （回合停在等用户决定时不生成，见 `isTurnWaitingForUser`）。
 */
import { Message } from '@/store/chat/types';
import useBrowserTakeoverStore from '../useBrowserTakeoverStore';
import useConfigStore from '../useConfigStore';
import useDesktopControlApprovalStore from '../useDesktopControlApprovalStore';
import useToolApprovalStore from '../useToolApprovalStore';
import { getSuggestions as getSuggestionsService } from '@/services/chat';
import { buildSimpleChatHistory } from './chatHistoryBuilder';

/**
 * 查找指定messageId的assistant消息索引
 */
export const findAssistantMessageIndex = (messages: Message[], messageId: string): number => {
  return messages.findIndex((msg) => msg.messageId === messageId && msg.role === 'assistant');
};

/**
 * 移除某条消息上的 waiting_for_turn 进度步骤。
 *
 * 用户在前端取消请求时，后端 pump 可能在取得项目锁之前就退出了，
 * 不会再发出 waiting_for_turn_clear SSE；本地残留的等待步骤在此清除。
 * 返回新数组（immutable），无匹配时原样返回。
 */
export const removeWaitingForTurnStep = (messages: Message[], messageId: string): Message[] => {
  const next = messages.map((msg) => {
    if (msg.messageId !== messageId || !msg.progressSteps?.length) {
      return msg;
    }
    const hasWaitingStep = msg.progressSteps.some((step) => step.step_key === 'waiting_for_turn');
    if (!hasWaitingStep) {
      return msg;
    }
    return {
      ...msg,
      progressSteps: msg.progressSteps.filter((step) => step.step_key !== 'waiting_for_turn'),
    };
  });
  const changed = next.some((msg, index) => msg !== messages[index]);
  return changed ? next : messages;
};

/**
 * Ensure an assistant placeholder exists for stream events that may arrive before MESSAGE.
 * Returns the message index, or -1 when messageId is missing.
 */
export const ensureAssistantStreamMessage = (
  messages: Message[],
  messageId: string | undefined,
  chatIdFallback: string,
): number => {
  const normalizedId = messageId?.trim();
  if (!normalizedId) {
    return -1;
  }
  const existing = findAssistantMessageIndex(messages, normalizedId);
  if (existing !== -1) {
    return existing;
  }
  messages.push({
    content: '',
    messageId: normalizedId,
    chatId: chatIdFallback,
    role: 'assistant',
    progressSteps: [],
    createdAt: new Date(),
  });
  return messages.length - 1;
};

/**
 * Drop a half-streamed assistant draft before a recovery that restarts the turn.
 *
 * The harness re-runs the answer from scratch after model failover, transient
 * retry, context compaction, escalation, etc., and emits the recovery event
 * before the restreamed chunks arrive. Clearing the accumulated content /
 * reasoning here (and resetting the reasoning timer) keeps the UI from
 * splicing the stale partial draft with the complete re-generated answer.
 * Idempotent: a second recovery event finds an empty buffer.
 */
export const clearAssistantDraft = (message: Message): void => {
  message.content = '';
  message.reasoning = '';
  message.reasoningStartedAt = undefined;
  message.reasoningDurationMs = undefined;
};

/** Stream-level draft buffers reset by a recovery that re-runs the turn. */
export interface StreamDraftBuffers {
  recievedMessage: string;
  state: { scheduler?: { cancel?: () => void } };
}

/**
 * Drop the stream-level draft before a recovery restarts the turn.
 *
 * Complements `clearAssistantDraft` (message-level): resets the accumulated
 * chunk buffer and cancels any pending render task whose closure captured the
 * pre-clear buffer and would write the stale draft back to the message.
 */
export const discardStreamedDraft = (ctx: StreamDraftBuffers): void => {
  ctx.recievedMessage = '';
  ctx.state.scheduler?.cancel?.();
};

/** Answers whose follow-ups are being requested; a repeated terminal event must not ask the model twice. */
const suggestionsInFlight = new Set<string>();

/** The server reads only this many trailing messages (`_HISTORY_MESSAGES`); the rest of a long chat is upload for nothing. */
const SUGGESTION_CONTEXT_MESSAGES = 6;

/**
 * Whether the turn that just ended stopped to ask the user for a decision (approval, question, plan, takeover).
 *
 * Scoped to this turn: a decision another chat or a background task is waiting for must not silence this chat's
 * follow-ups, so the companion's global "blocked on user" flag is not reused. A generic approval carries no message
 * id and is matched on the chat.
 */
const isTurnWaitingForUser = async (turn: Message): Promise<boolean> => {
  if (
    (turn.clarification && !turn.clarification.answered) ||
    turn.planConfirmation?.status === 'waiting' ||
    turn.humanGate?.status === 'waiting'
  ) {
    return true;
  }
  const desktopControl = useDesktopControlApprovalStore.getState();
  const browserTakeover = useBrowserTakeoverStore.getState();
  if (
    useToolApprovalStore.getState().queue.some((request) => request.messageId === turn.messageId) ||
    (desktopControl.pending && desktopControl.messageId === turn.messageId) ||
    (browserTakeover.pending && browserTakeover.messageId === turn.messageId)
  ) {
    return true;
  }
  // The approval store imports the chat store, which imports this module: loaded on demand to keep the graph acyclic.
  const { default: useApprovalStore } = await import('@/store/useApprovalStore');
  return useApprovalStore.getState().queue.some((approval) => approval.chat_id === turn.chatId);
};

/**
 * 处理建议生成
 *
 * 搜索模式和 Agent 模式均支持。后端从 DB 读取 filter model 配置。
 */
export const processSuggestions = async (
  lastMsg: Message,
  messages: Message[],
  updateMessage: (messageId: string, suggestions: string[]) => void,
): Promise<void> => {
  const configStore = useConfigStore.getState();
  if (!configStore.generateSearchSuggestions) {
    return;
  }

  // A turn can finish in a pane other than the one the store shows: its history is not in `messages`, so the
  // follow-ups would be generated from, and filed under, the wrong chat.
  if (!messages.some((message) => message.messageId === lastMsg.messageId)) {
    return;
  }

  if (lastMsg.role !== 'assistant' || lastMsg.content.trim().length === 0 || lastMsg.suggestions) {
    return;
  }
  // A turn that stopped for the user's decision has no finished answer yet; the resumed turn asks when it ends.
  // A check that cannot be evaluated must not cost the user their follow-ups, and the caller does not await us.
  const waitingForUser = await isTurnWaitingForUser(lastMsg).catch((error: unknown) => {
    console.warn('Could not tell whether the turn is waiting for the user:', error);
    return false;
  });
  if (waitingForUser) {
    return;
  }
  if (suggestionsInFlight.has(lastMsg.messageId)) {
    return;
  }

  suggestionsInFlight.add(lastMsg.messageId);
  try {
    const suggestions = await getSuggestionsService(
      buildSimpleChatHistory(messages.slice(-SUGGESTION_CONTEXT_MESSAGES)),
    );
    updateMessage(lastMsg.messageId, suggestions);
  } catch (error) {
    console.error('Failed to get suggestions:', error);
  } finally {
    suggestionsInFlight.delete(lastMsg.messageId);
  }
};
