'use client';

import { useLayoutEffect } from 'react';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';

/**
 * Binds the goal store to the open chat and loads that chat's goal and queue.
 *
 * A layout effect, so the goal of the chat that was open before is gone before the new chat paints; what the old chat's
 * requests bring back afterwards is dropped by the store because it is no longer bound to that chat.
 */
export function useGoalSync(chatId: string | null | undefined): void {
  useLayoutEffect(() => {
    const store = useGoalStore.getState();
    store.bindChat(chatId || null);
    if (!chatId) {
      return;
    }
    void store.refreshActiveGoal(chatId);
    void store.fetchQueue(chatId);
  }, [chatId]);
}
