/**
 * [INPUT]
 * @/store/useChatStore::initializeChat (POS: Active chat state manager)
 * @/store/useWorkspaceStore::addPane (POS: Multi-pane workspace)
 *
 * [OUTPUT]
 * ensureActiveChatId: Returns existing chat id or creates a new chat + pane.
 *
 * [POS]
 * Shared chat session bootstrap for programmatic sends from Settings panels.
 */

export async function ensureActiveChatId(): Promise<string | null> {
  const { default: useChatStore } = await import('@/store/useChatStore');
  let { chatId } = useChatStore.getState();
  if (chatId?.trim()) {
    return chatId;
  }

  useChatStore.getState().initializeChat(undefined);
  chatId = useChatStore.getState().chatId;
  if (!chatId?.trim()) {
    return null;
  }

  const { default: useWorkspaceStore } = await import('@/store/useWorkspaceStore');
  const panes = useWorkspaceStore.getState().panes;
  const hasPane = panes.some((pane) => pane.chatId === chatId);
  if (!hasPane) {
    useWorkspaceStore.getState().addPane(chatId);
  }

  return chatId;
}
