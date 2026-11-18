/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: 带鉴权与错误归一的 API 请求)
 *
 * [OUTPUT]
 * - SearchResult / SearchResponse: 历史消息检索的命中项与响应
 * - searchChatHistory: Cmd+K 历史消息全文检索
 * - searchCitableChats: 输入框 `@chat:` 引用候选检索（与服务端注入走同一召回索引）
 *
 * [POS]
 * 会话历史检索的前端服务：全文检索与 `@chat:` 引用候选共用同一份命中项契约。
 */

import { apiRequest } from '@/lib/api';

export interface SearchResult {
  id: string;
  chat_id: string;
  role: string;
  content: string;
  sent_at: string;
  chat_title: string | null;
  snippet: string;
  source?: string;
}

export interface SearchResponse {
  items: SearchResult[];
  total: number;
}

export const searchChatHistory = async (
  query: string,
  limit: number = 20,
  offset: number = 0,
  since?: string,
  until?: string,
): Promise<SearchResponse> => {
  const params = new URLSearchParams({ q: query, limit: String(limit), offset: String(offset) });
  if (since) {
    params.set('since', since);
  }
  if (until) {
    params.set('until', until);
  }
  const data = (await apiRequest(`/chats/search?${params}`)) as SearchResponse;
  return { items: data.items || [], total: data.total || 0 };
};

/** Recall-index SSOT search for @chat: composer citation (matches server inject path). */
export const searchCitableChats = async (
  query: string,
  limit: number = 20,
  offset: number = 0,
  excludeChatId?: string,
): Promise<SearchResponse> => {
  const params = new URLSearchParams({ q: query, limit: String(limit), offset: String(offset) });
  if (excludeChatId) {
    params.set('exclude_chat_id', excludeChatId);
  }
  const data = (await apiRequest(`/chats/recall/search?${params}`)) as SearchResponse;
  return { items: data.items || [], total: data.total || 0 };
};
