import { ApiError, apiRequest } from '@/lib/api';

export interface ConversationPurgeResult {
  purged_chats: number;
  purged_messages: number;
  cleared_sandboxes: number;
}

/** The server refuses to purge while a conversation has a turn in flight. */
export class ConversationPurgeBusyError extends Error {
  constructor() {
    super('A conversation is still running');
    this.name = 'ConversationPurgeBusyError';
  }
}

// Spans a large vault: the server removes every chat's files before it answers.
const PURGE_TIMEOUT_MS = 300_000;

/**
 * Deletes every conversation and the files they produced.
 * Memories, agents, API keys and channel settings are kept by the server.
 * Failures are left to the caller to report (`silent`).
 */
export const purgeAllConversations = async (): Promise<ConversationPurgeResult> => {
  try {
    return await apiRequest<ConversationPurgeResult>('/health/database/safe-purge', {
      method: 'POST',
      silent: true,
      timeout: PURGE_TIMEOUT_MS,
    });
  } catch (error) {
    if (error instanceof ApiError && error.code === 409) {
      throw new ConversationPurgeBusyError();
    }
    throw error;
  }
};
