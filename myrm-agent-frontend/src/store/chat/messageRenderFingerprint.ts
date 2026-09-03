import type { Message } from '@/store/chat/types';

/** Fingerprint for message list re-render; must include sources so citation UI refreshes after SSE. */
export function buildMessageRenderFingerprint(messages: Pick<Message, 'messageId' | 'content' | 'sources'>[]): string {
  return messages.map((m) => `${m.messageId}:${m.content?.length || 0}:${m.sources?.length || 0}`).join('|');
}
