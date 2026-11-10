/**
 * [INPUT]
 * - ./chatRouteHydration (POS: 路由会话是否已水合的判定与订阅)
 * - @/store/useChatStore (POS: 会话 id、消息与加载状态)
 * - @/hooks/shared/useStoreSnapshot (POS: 流式热路径的手动订阅)
 *
 * [OUTPUT]
 * - useChatRouteHydration: 窗口渲染所需的水合派生状态（消息、是否已水合、重建聊天视图的序号）
 *
 * [POS]
 * ChatWindow 的水合层。聊天视图在会话加载完成时整体重建，其余 store 写入必须让它保持挂载：
 * routeHydrationEpoch 只在「水合答案翻转」或 E2E 水合信号到达时推进。
 */

import { useEffect, useState, useSyncExternalStore } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { useStoreSnapshot } from '@/hooks/shared/useStoreSnapshot';
import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import { isChatRouteHydratedForId, subscribeChatRouteHydrated } from './chatRouteHydration';

export interface ChatRouteHydration {
  chatMessages: Message[];
  chatMessagesForRender: Message[];
  chatRouteHydrated: boolean;
  routeHydrationEpoch: number;
}

export function useChatRouteHydration(id: string | undefined): ChatRouteHydration {
  const [routeHydrationEpoch, setRouteHydrationEpoch] = useState(0);
  const { compactedSummary, storeChatId, isMessagesLoaded } = useChatStore(
    useShallow((state) => ({
      compactedSummary: state.compactedSummary,
      storeChatId: state.chatId,
      isMessagesLoaded: state.isMessagesLoaded,
    })),
  );

  // The chat view is re-created when the conversation finishes loading; any other store write must leave it mounted.
  useEffect(() => subscribeChatRouteHydrated(id, () => setRouteHydrationEpoch((epoch) => epoch + 1)), [id]);

  useEffect(() => {
    if (!id) {
      return;
    }
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ chatId?: string }>).detail;
      if (detail?.chatId !== id) {
        return;
      }
      setRouteHydrationEpoch((epoch) => epoch + 1);
    };
    window.addEventListener('myrm-e2e-chat-route-hydrated', handler);
    return () => window.removeEventListener('myrm-e2e-chat-route-hydrated', handler);
  }, [id]);

  const chatMessages = useStoreSnapshot(
    (onStoreChange) => useChatStore.subscribe(onStoreChange),
    () => useChatStore.getState().messages,
    () => [],
    id,
  );

  const chatRouteHydratedFromSelector =
    Boolean(id) &&
    storeChatId === id &&
    isMessagesLoaded &&
    (chatMessages.length > 0 || Boolean(compactedSummary?.trim()));

  const chatRouteHydratedDirect = Boolean(id) && isChatRouteHydratedForId(id);

  const chatRouteHydratedSync = useSyncExternalStore(
    (onStoreChange) => subscribeChatRouteHydrated(id, onStoreChange),
    () => isChatRouteHydratedForId(id),
    () => false,
  );

  // `isChatRouteHydratedForId` reads `useChatStore.getState()` directly, so a
  // pre-populated store (previous chat kept across navigation) makes it report
  // `true` before React has hydrated. On the server / first client render that
  // disagrees with the hydration-safe `getServerSnapshot` (`false`), flipping
  // the skeleton subtree in `renderChatContent` and failing hydration
  // (`clientHydrated: false` → E2E bridge never becomes ready). Only trust the
  // direct read once we are actually on the client.
  const isClientHydrated = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );

  const storeMessagesDirect = id && useChatStore.getState().chatId === id ? useChatStore.getState().messages : [];

  const chatMessagesForRender = chatMessages.length > 0 ? chatMessages : storeMessagesDirect;

  const chatRouteHydrated =
    chatRouteHydratedSync || (isClientHydrated && (chatRouteHydratedFromSelector || chatRouteHydratedDirect));

  return {
    chatMessages,
    chatMessagesForRender,
    chatRouteHydrated,
    routeHydrationEpoch,
  };
}
