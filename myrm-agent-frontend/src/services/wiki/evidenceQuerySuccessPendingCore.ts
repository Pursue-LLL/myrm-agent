/**
 * [INPUT]
 * - chatId / expectedMessageId（POS: chat 会话标识与预期流 messageId）
 * - contextKey / turnDistance（POS: Wiki query success 口径上下文）
 *
 * [OUTPUT]
 * - queuePendingChatWikiQuerySuccess: 注册待确认的 chat query success（steer 路径）。
 * - consumePendingChatWikiQuerySuccess: 在流式业务帧到达时消费并返回待上报上下文。
 *
 * [POS]
 * Chat Wiki query success 延迟确认核心。用于把 steer 成功从“HTTP accepted”语义提升为
 * “业务帧已到达”语义，避免 success 指标提前误计。
 */

const PENDING_CHAT_QUERY_SUCCESS_TTL_MS = 120_000;

export interface PendingChatWikiQuerySuccessContext {
  contextKey: string | undefined;
  turnDistance: number | undefined;
}

interface PendingChatWikiQuerySuccessRecord extends PendingChatWikiQuerySuccessContext {
  expectedMessageId: string | undefined;
  expiresAtMs: number;
}

const pendingByChatId = new Map<string, PendingChatWikiQuerySuccessRecord>();

function normalizeNonEmptyString(value: string | undefined): string | undefined {
  const normalized = value?.trim();
  return normalized && normalized.length > 0 ? normalized : undefined;
}

function pruneExpiredPending(nowMs: number): void {
  for (const [chatId, record] of pendingByChatId.entries()) {
    if (record.expiresAtMs <= nowMs) {
      pendingByChatId.delete(chatId);
    }
  }
}

export function queuePendingChatWikiQuerySuccess(
  chatId: string | undefined,
  context: PendingChatWikiQuerySuccessContext,
  expectedMessageId?: string,
): void {
  const normalizedChatId = normalizeNonEmptyString(chatId);
  if (!normalizedChatId) {
    return;
  }
  const nowMs = Date.now();
  pruneExpiredPending(nowMs);
  pendingByChatId.set(normalizedChatId, {
    contextKey: context.contextKey,
    turnDistance: context.turnDistance,
    expectedMessageId: normalizeNonEmptyString(expectedMessageId),
    expiresAtMs: nowMs + PENDING_CHAT_QUERY_SUCCESS_TTL_MS,
  });
}

export function consumePendingChatWikiQuerySuccess(
  chatId: string | undefined,
  currentMessageId?: string,
): PendingChatWikiQuerySuccessContext | undefined {
  const normalizedChatId = normalizeNonEmptyString(chatId);
  if (!normalizedChatId) {
    return undefined;
  }
  const nowMs = Date.now();
  pruneExpiredPending(nowMs);
  const pending = pendingByChatId.get(normalizedChatId);
  if (!pending) {
    return undefined;
  }

  const normalizedCurrentMessageId = normalizeNonEmptyString(currentMessageId);
  if (pending.expectedMessageId && pending.expectedMessageId !== normalizedCurrentMessageId) {
    return undefined;
  }

  pendingByChatId.delete(normalizedChatId);
  return {
    contextKey: pending.contextKey,
    turnDistance: pending.turnDistance,
  };
}

export function __resetPendingChatWikiQuerySuccessForTest(): void {
  pendingByChatId.clear();
}
