/**
 * [INPUT]
 * - @/store/useChatStore (POS: chat id, the chat-level abort controller, server-reported session status)
 * - @/store/useWorkspaceStore (POS: the abort controller of the pane that shows the chat)
 * - @/store/chat/serverTurn::selectChatGenerating (POS: a turn the server runs without a controller in this client)
 *
 * [OUTPUT]
 * - useTurnStoppable: whether the open chat has a turn that Stop can reach
 *
 * [POS]
 * `loading` also covers the load of a chat's history, when no turn is attached yet: Stop pressed then reaches nothing.
 * The controls that offer Stop read this instead of `loading`; it holds exactly when `stopMessage` has a turn to stop.
 */
import { selectChatGenerating } from '@/store/chat/serverTurn';
import useChatStore from '@/store/useChatStore';
import useWorkspaceStore from '@/store/useWorkspaceStore';

export const useTurnStoppable = (): boolean => {
  const chatId = useChatStore((state) => state.chatId);
  const hasChatController = useChatStore((state) => Boolean(state.abortController));
  const serverTurnActive = useChatStore(selectChatGenerating);
  const hasPaneController = useWorkspaceStore(
    (state) => state.panes.find((pane) => pane.chatId === chatId)?.abortController != null,
  );
  return hasChatController || hasPaneController || serverTurnActive;
};
