/**
 * [INPUT]
 * - @/store/chat/types::Message, Source (POS: 持久化与渲染用的聊天消息实体 / 消息引用来源与 citation 契约)
 * - @/services/wikiEvidenceMetrics::recordWikiQueryAttempt/recordWikiQuerySubmitted (POS: Wiki 证据指标采集客户端)
 *
 * [OUTPUT]
 * - resolveChatWikiEvidenceContext: 解析 chat 发送侧的 wiki query context（含 turn_distance）。
 * - recordChatWikiQueryAttempt: 统一上报 chat query_attempted 指标。
 * - recordChatWikiQuerySubmitted: 统一上报 chat query_submitted(success) 指标。
 *
 * [POS]
 * Chat 输入链路的 Wiki 证据复问口径核心。将消息上下文解析与 attempt/success 指标上报从 UI Hook 中剥离，保证语义稳定与可测试性。
 */
import type { Message, Source } from '@/store/chat/types';
import { recordWikiQueryAttempt, recordWikiQuerySubmitted } from '@/services/wikiEvidenceMetrics';

const MAX_CONTEXT_ASSISTANT_TURN_DISTANCE = 8;

export interface ChatWikiEvidenceContext {
  contextKey: string | undefined;
  turnDistance: number | undefined;
}

function hasKbEvidence(sources: Source[] | undefined): boolean {
  if (!Array.isArray(sources) || sources.length === 0) {
    return false;
  }
  return sources.some((source) => Boolean(source.kb_name) && Boolean(source.snippet || source.summary));
}

export function resolveChatWikiEvidenceContext(messages: Message[], chatId: string | undefined): ChatWikiEvidenceContext {
  const normalizedChatId = chatId?.trim();
  if (!normalizedChatId) {
    return { contextKey: undefined, turnDistance: undefined };
  }

  let assistantTurnDistance = 0;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (!message || message.role !== 'assistant') {
      continue;
    }
    if (assistantTurnDistance > MAX_CONTEXT_ASSISTANT_TURN_DISTANCE) {
      break;
    }
    if (message.messageId && hasKbEvidence(message.sources)) {
      return {
        contextKey: `chat:${message.messageId}`,
        turnDistance: assistantTurnDistance,
      };
    }
    assistantTurnDistance += 1;
  }

  return {
    contextKey: `chat:${normalizedChatId}`,
    turnDistance: undefined,
  };
}

export function recordChatWikiQueryAttempt(messages: Message[], chatId: string | undefined): void {
  const context = resolveChatWikiEvidenceContext(messages, chatId);
  recordWikiQueryAttempt('chat', context.contextKey, context.turnDistance);
}

export function recordChatWikiQuerySubmitted(messages: Message[], chatId: string | undefined): void {
  const context = resolveChatWikiEvidenceContext(messages, chatId);
  recordWikiQuerySubmitted('chat', context.contextKey, context.turnDistance);
}
