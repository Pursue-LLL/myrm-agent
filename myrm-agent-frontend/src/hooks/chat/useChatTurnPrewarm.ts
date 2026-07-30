/**
 * [INPUT]
 * - @/services/chat::startChatTurnPrewarm, cancelChatTurnPrewarm (POS: prewarm REST)
 * - @/store/useChatStore (POS: chatId / agent / mode)
 *
 * [OUTPUT]
 * - useChatTurnPrewarm: trigger/cancel idempotent turn prewarm for cold turn1.
 *
 * [POS]
 * EmptyChat mount + MessageInput focus + agent switch proactive warm hook.
 * Module-level inflight map dedupes POST across multiple hook instances on one page.
 * autoOnMount does not cancel on unmount so first-send EmptyChat→Chat transition keeps warm alive.
 */
import { useCallback, useEffect } from 'react';

import { cancelChatTurnPrewarm, startChatTurnPrewarm } from '@/services/chat';
import useChatStore from '@/store/useChatStore';

type UseChatTurnPrewarmOptions = {
  autoOnMount?: boolean;
};

type PrewarmScope = {
  chatId: string;
  agentId: string | null;
  actionMode: string;
  incognitoMode: boolean;
};

function buildPrewarmScopeKey(scope: PrewarmScope): string {
  return `${scope.chatId}:${scope.agentId ?? ''}:${scope.actionMode}`;
}

const moduleInflightPrewarm = new Map<string, Promise<void>>();

/** Clears module inflight map — for unit tests only. */
export function resetTurnPrewarmInflightForTests(): void {
  moduleInflightPrewarm.clear();
}

function clearModuleInflightForChat(chatId: string, agentId: string | null): void {
  const prefix = `${chatId}:${agentId ?? ''}:`;
  for (const key of moduleInflightPrewarm.keys()) {
    if (key.startsWith(prefix)) {
      moduleInflightPrewarm.delete(key);
    }
  }
}

async function runPrewarmOnce(scope: PrewarmScope): Promise<void> {
  const scopeKey = buildPrewarmScopeKey(scope);
  const existing = moduleInflightPrewarm.get(scopeKey);
  if (existing) {
    await existing;
    return;
  }

  const task = startChatTurnPrewarm(scope.chatId, {
    agentId: scope.agentId,
    actionMode: scope.actionMode,
    incognitoMode: scope.incognitoMode,
  })
    .then(() => undefined)
    .catch(() => undefined)
    .finally(() => {
      if (moduleInflightPrewarm.get(scopeKey) === task) {
        moduleInflightPrewarm.delete(scopeKey);
      }
    });

  moduleInflightPrewarm.set(scopeKey, task);
  await task;
}

export function useChatTurnPrewarm(options: UseChatTurnPrewarmOptions = {}) {
  const { autoOnMount = false } = options;
  const chatId = useChatStore((s) => s.chatId);
  const actionMode = useChatStore((s) => s.actionMode);
  const incognitoMode = useChatStore((s) => s.incognitoMode);
  const agentId = useChatStore((s) => s.agentConfig?.agentId ?? null);

  const shouldPrewarm = Boolean(chatId) && actionMode !== 'fast' && !incognitoMode;

  const triggerPrewarm = useCallback(async () => {
    if (!shouldPrewarm || !chatId) {
      return;
    }
    await runPrewarmOnce({
      chatId,
      agentId,
      actionMode,
      incognitoMode,
    });
  }, [actionMode, agentId, chatId, incognitoMode, shouldPrewarm]);

  const cancelPrewarm = useCallback(async () => {
    if (!chatId) {
      return;
    }
    clearModuleInflightForChat(chatId, agentId);
    try {
      await cancelChatTurnPrewarm(chatId, agentId);
    } catch {
      /* blur cancel is best-effort */
    }
  }, [agentId, chatId]);

  useEffect(() => {
    if (!autoOnMount || !shouldPrewarm) {
      return;
    }
    void triggerPrewarm();
  }, [autoOnMount, shouldPrewarm, chatId, agentId, actionMode, triggerPrewarm]);

  return { triggerPrewarm, cancelPrewarm, shouldPrewarm };
}
