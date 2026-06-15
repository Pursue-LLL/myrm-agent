/**
 * Conversation Fork API Client
 *
 * Provides API wrappers for conversation forking endpoints.
 */

import { apiRequest } from '@/lib/api';

/**
 * Fork conversation request parameters
 */
export interface ForkConversationRequest {
  message_index: number;
  new_title?: string;
}

/**
 * Fork conversation response
 */
export interface ForkConversationResponse {
  success: boolean;
  data: {
    new_chat_id: string;
    parent_chat_id: string;
    fork_point: number;
  };
}

/**
 * Fork info response
 */
export interface ForkInfoResponse {
  success: boolean;
  data: {
    parent_chat_id: string | null;
    fork_point: number | null;
    children: Array<{
      chat_id: string;
      title: string;
      created_at: string;
    }>;
  };
}

/**
 * Fork conversation from specific message index
 */
export async function forkConversation(
  chatId: string,
  messageIndex: number,
  newTitle?: string,
): Promise<ForkConversationResponse> {
  return apiRequest<ForkConversationResponse>(`/chats/${chatId}/fork`, {
    method: 'POST',
    body: JSON.stringify({ message_index: messageIndex, new_title: newTitle }),
  });
}

/**
 * Get fork relationship information
 */
export async function getForkInfo(chatId: string): Promise<ForkInfoResponse> {
  return apiRequest<ForkInfoResponse>(`/chats/${chatId}/fork-info`);
}
