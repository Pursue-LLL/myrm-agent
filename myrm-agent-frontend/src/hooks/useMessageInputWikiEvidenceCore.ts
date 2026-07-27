/**
 * [INPUT]
 * - @/store/chat/types::Message, Source (POS: 持久化与渲染用的聊天消息实体 / 消息引用来源与 citation 契约)
 * - @/services/wikiEvidenceContextCore::resolveChatWikiEvidenceContext (POS: Wiki 证据 query 上下文解析核心)
 * - @/services/wikiEvidenceMetrics::recordWikiQueryAttempt/recordWikiQuerySubmitted (POS: Wiki 证据指标采集客户端)
 *
 * [OUTPUT]
 * - resolveChatWikiEvidenceContext: 解析 chat 发送侧的 wiki query context（含 turn_distance）。
 * - recordChatWikiQueryAttempt: 统一上报 chat query_attempted 指标。
 * - recordChatWikiQuerySubmitted: 统一上报 chat query_submitted(success) 指标。
 *
 * [POS]
 * Chat 输入链路的 Wiki 证据复问口径包装层。复用 service core 做上下文解析，并统一触发 attempt/success 指标上报。
 */
import type { Message } from '@/store/chat/types';
import { resolveChatWikiEvidenceContext } from '@/services/wikiEvidenceContextCore';
import { recordWikiQueryAttempt, recordWikiQuerySubmitted } from '@/services/wikiEvidenceMetrics';

export { resolveChatWikiEvidenceContext };

export function recordChatWikiQueryAttempt(messages: Message[], chatId: string | undefined): void {
  const context = resolveChatWikiEvidenceContext(messages, chatId);
  recordWikiQueryAttempt('chat', context.contextKey, context.turnDistance);
}

export function recordChatWikiQuerySubmitted(messages: Message[], chatId: string | undefined): void {
  const context = resolveChatWikiEvidenceContext(messages, chatId);
  recordWikiQuerySubmitted('chat', context.contextKey, context.turnDistance);
}
