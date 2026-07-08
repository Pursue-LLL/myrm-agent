/**
 * [INPUT]
 * @/store/useChatStore::useChatStore (POS: Chat session state store)
 * @/store/chat/types::Message (POS: chat message entity)
 * @/store/chat/types/pendingGapRetry::PendingGapRetry (POS: deferred gap retry contract type)
 *
 * [OUTPUT]
 * resolveLastPlainUserMessage: extract retryable user text
 * flushPendingGapRetry: send deferred message when entitlement is satisfied
 * scheduleFlushPendingGapRetry: defer flush until stream loading has settled
 *
 * [POS]
 * Bridges capability/skill gap toasts with stream loading lifecycle so gap retries
 * do not fail when preflight fires at the start of an in-flight agent stream.
 */

import type { Message } from '@/store/chat/types';
import type { PendingGapRetry } from '@/store/chat/types/pendingGapRetry';
import useChatStore from '@/store/useChatStore';

export type { PendingGapRetry };

function createRetryMessageId(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  return `gap-retry-${Date.now()}`;
}

export function resolveLastPlainUserMessage(messages: Message[]): string | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== 'user') {
      continue;
    }
    const content = message.content;
    if (typeof content === 'string' && content.trim()) {
      return content.trim();
    }
  }
  return null;
}

function isPendingGapRetrySatisfied(pending: PendingGapRetry): boolean {
  const store = useChatStore.getState();
  if (pending.kind === 'capability') {
    return store.currentBuiltinTools.includes(pending.toolId);
  }
  const skillIds = store.agentConfig?.selectedSkillIds ?? [];
  return skillIds.includes(pending.skillId);
}

export async function flushPendingGapRetry(): Promise<boolean> {
  const store = useChatStore.getState();
  const pending = store.pendingGapRetry;
  if (!pending || store.loading) {
    return false;
  }
  if (!isPendingGapRetrySatisfied(pending)) {
    return false;
  }
  await store.sendMessage(pending.text, createRetryMessageId());
  store.clearPendingGapRetry();
  return true;
}

export function scheduleFlushPendingGapRetry(): void {
  void Promise.resolve().then(() => flushPendingGapRetry());
}
