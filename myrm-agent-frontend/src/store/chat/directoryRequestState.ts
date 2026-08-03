/**
 * Shared directory-request state helpers for message hydrate and composer takeover selection.
 */

import type { Message } from './types';

export function normalizeHydratedDirectoryRequest(
  directoryRequest: NonNullable<Message['directoryRequest']>,
): NonNullable<Message['directoryRequest']> {
  if (directoryRequest.answered !== true) {
    directoryRequest.answered = false;
  }
  if (directoryRequest.isResumeMode === undefined) {
    directoryRequest.isResumeMode = true;
  }
  return directoryRequest;
}

export function findActivePendingDirectoryRequest(
  messages: Message[],
): { messageId: string; directoryRequest: NonNullable<Message['directoryRequest']> } | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== 'assistant') {
      continue;
    }
    if (message.directoryRequest && !message.directoryRequest.answered) {
      return { messageId: message.messageId, directoryRequest: message.directoryRequest };
    }
  }
  return null;
}
