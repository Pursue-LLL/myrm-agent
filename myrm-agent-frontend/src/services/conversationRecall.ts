/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: 前端 API 接入层)
 * - @/services/chat::PaginationInfo (POS: 会话 REST 客户端与分页契约)
 *
 * [OUTPUT]
 * - updateChatRecallExclusion: 把会话从模型可召回的范围排除或恢复。
 * - listConversationRecallEntries / ConversationRecallEntry / ConversationRecallListResponse: 管理面板的已索引会话分页列表，每条只带最后一条消息的时间。
 *
 * [POS]
 * Conversation Recall 管理 API 客户端。
 */

import { apiRequest } from '@/lib/api';
import type { PaginationInfo } from '@/services/chat';

/**
 * 从 Conversation Recall 中排除或恢复聊天。
 */
export const updateChatRecallExclusion = async (chatId: string, excluded: boolean): Promise<void> => {
  await apiRequest(`/chats/${chatId}/recall-exclusion`, {
    method: 'PATCH',
    body: JSON.stringify({ excluded }),
  });
};

export interface ConversationRecallEntry {
  chat_id: string;
  title: string | null;
  agent_id: string | null;
  source: string;
  snippet: string;
  summary: string | null;
  last_message_at: string | null;
  is_excluded: boolean;
}

export interface ConversationRecallListResponse {
  items: ConversationRecallEntry[];
  pagination: PaginationInfo;
}

export const listConversationRecallEntries = async (params: {
  excluded?: boolean;
  page?: number;
  pageSize?: number;
}): Promise<ConversationRecallListResponse> => {
  const query = new URLSearchParams({
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 20),
  });
  if (params.excluded !== undefined) {
    query.set('excluded', String(params.excluded));
  }
  const data = (await apiRequest(`/chats/recall/entries?${query}`)) as ConversationRecallListResponse;
  return {
    items: data.items || [],
    pagination: data.pagination,
  };
};
