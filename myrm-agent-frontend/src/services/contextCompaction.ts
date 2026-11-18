/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: 带鉴权与错误归一的 API 请求)
 * - @/lib/constants/compact-focus-topic::COMPACT_FOCUS_TOPIC_MAX_LENGTH (POS: 服务端接受的聚焦主题最大长度)
 * - @/lib/utils/firstChars::firstChars (POS: 按字符数截断文本，不拆开一个字符)
 *
 * [OUTPUT]
 * - CompactResult: 一次手动压缩上下文的结果
 * - compactChat: 压缩会话上下文，可带聚焦主题
 *
 * [POS]
 * 上下文压缩的前端服务。聚焦主题发出前按服务端上限截断，所以输入框与 `/compact <主题>` 两条路径都不会被服务端拒收。
 */

import { apiRequest } from '@/lib/api';
import { COMPACT_FOCUS_TOPIC_MAX_LENGTH } from '@/lib/constants/compact-focus-topic';
import { firstChars } from '@/lib/utils/firstChars';

export interface CompactResult {
  compacted: boolean;
  message_count: number;
  tokens_saved: number;
  reason: string | null;
  focus_topic?: string;
  backup_path?: string | null;
}

export const compactChat = async (chatId: string, focusTopic?: string): Promise<CompactResult> => {
  // The server refuses a longer topic (HTTP 422); a topic typed after `/compact` has no box to stop it, so it is cut here.
  const body = focusTopic
    ? JSON.stringify({ focus_topic: firstChars(focusTopic, COMPACT_FOCUS_TOPIC_MAX_LENGTH) })
    : undefined;
  return (await apiRequest(`/chats/${chatId}/compact`, {
    method: 'POST',
    ...(body ? { body, headers: { 'Content-Type': 'application/json' } } : {}),
  })) as CompactResult;
};
