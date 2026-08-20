/**
 * [INPUT]
 * - @/store/chat/types::Message, Source (POS: 持久化与渲染用的聊天消息实体 / 消息引用来源与 citation 契约)
 *
 * [OUTPUT]
 * - resolveChatWikiEvidenceContext: 解析 chat 发送侧 wiki query context（`contextKey` + `turnDistance`）。
 *
 * [POS]
 * Wiki 证据 query 上下文解析核心。为 chat 输入与流式请求链路提供统一的 context 回溯边界语义，避免口径漂移。
 */
import type { Message, Source } from '@/store/chat/types';

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

export function resolveChatWikiEvidenceContext(
  messages: Message[],
  chatId: string | undefined,
): ChatWikiEvidenceContext {
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
