/**
 * [INPUT]
 * - @/services/chat::getChatDetail (POS: Chat API client)
 * - @/store/useChatStore::setSessionAccessRoots (POS: chat 行级 session_access_roots 状态)
 * - @/store/chat/types/sessionAccess::normalizeSessionAccessRoots (POS: API JSON → SessionAccessRoot[])
 *
 * [OUTPUT]
 * - refreshSessionAccessRoots: 从 chat detail 刷新 store 中的 sessionAccessRoots（SSOT）
 *
 * [POS]
 * 会话目录 grant/revoke 后 FE store 与 DB 对齐的单一刷新入口；path-ASK 与 request_directory HITL 共用。
 */

import { getChatDetail } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import {
  normalizeSessionAccessRoots,
  type SessionAccessRoot,
} from '@/store/chat/types/sessionAccess';

export interface RefreshSessionAccessRootsOptions {
  /** Applied when GET returns empty roots (eventual consistency after grant). */
  optimistic?: SessionAccessRoot;
}

export async function refreshSessionAccessRoots(
  chatId: string,
  options?: RefreshSessionAccessRootsOptions,
): Promise<void> {
  const optimistic = options?.optimistic;

  const applyOptimistic = () => {
    if (!optimistic) return;
    const current = useChatStore.getState().sessionAccessRoots;
    useChatStore.getState().setSessionAccessRoots([
      ...current.filter((root) => root.path !== optimistic.path),
      optimistic,
    ]);
  };

  try {
    const detail = await getChatDetail(chatId, true);
    const refreshed = normalizeSessionAccessRoots(detail.chat.session_access_roots);
    if (refreshed.length > 0 || !optimistic) {
      useChatStore.getState().setSessionAccessRoots(refreshed);
      return;
    }
    applyOptimistic();
  } catch (error) {
    console.warn('Failed to refresh session access roots:', error);
    applyOptimistic();
  }
}
