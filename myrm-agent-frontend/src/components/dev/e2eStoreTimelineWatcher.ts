/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 聊天 Zustand store 的业务分层)
 * - @/store/useWorkspaceStore::useWorkspaceStore (POS: 工作区 pane 状态)
 * - @/components/dev/e2eStoreTimeline::createStoreTimeline (POS: 消息列表变化记录)
 *
 * [OUTPUT]
 * - watchChatStoreTimeline: starts recording the chat store's message list changes until `stop`
 * - StoreTimelineWatch
 *
 * [POS]
 * Store-bound half of the E2E store timeline (the record itself is pure and unit-tested). Reads stores only;
 * it never writes them.
 */
import {
  createStoreTimeline,
  type StoreTimelineSample,
  type StoreTimelineSnapshot,
} from '@/components/dev/e2eStoreTimeline';
import type { ChatState } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import useWorkspaceStore from '@/store/useWorkspaceStore';

export interface StoreTimelineWatch {
  snapshot: () => StoreTimelineSnapshot;
  stop: () => void;
}

type WatchedFields = Pick<ChatState, 'chatId' | 'messages' | 'loading'>;

function sampleStores(state: WatchedFields): StoreTimelineSample {
  const workspace = useWorkspaceStore.getState();
  const activePane = workspace.panes.find((pane) => pane.id === workspace.activePaneId);
  let users = 0;
  let assistants = 0;
  for (const message of state.messages) {
    if (message.role === 'user') {
      users += 1;
    } else if (message.role === 'assistant') {
      assistants += 1;
    }
  }
  return {
    chatId: state.chatId?.trim() ?? '',
    paneChatId: activePane?.chatId?.trim() ?? '',
    users,
    assistants,
    loading: Boolean(state.loading),
  };
}

/**
 * The store notifies listeners synchronously inside the write, so the stack at that point names the writer. The
 * frames above `listener` (this diagnostic's own) are cut at the source where V8 allows. The capture runs inside the
 * store's write, so it must never throw into it.
 */
function captureWriterStack(listener: (...args: never[]) => void): string {
  try {
    if (typeof Error.captureStackTrace === 'function') {
      const holder: { stack?: string } = {};
      Error.captureStackTrace(holder, listener);
      return holder.stack ?? '';
    }
    return new Error().stack ?? '';
  } catch {
    return '';
  }
}

export function watchChatStoreTimeline(): StoreTimelineWatch {
  const timeline = createStoreTimeline(Date.now);
  timeline.observe(sampleStores(useChatStore.getState()), () => '');
  const onStoreChange = (state: WatchedFields, previous: WatchedFields): void => {
    if (
      state.messages === previous.messages &&
      state.chatId === previous.chatId &&
      state.loading === previous.loading
    ) {
      return;
    }
    timeline.observe(sampleStores(state), () => captureWriterStack(onStoreChange));
  };
  const stop = useChatStore.subscribe(onStoreChange);
  return { snapshot: timeline.snapshot, stop };
}
