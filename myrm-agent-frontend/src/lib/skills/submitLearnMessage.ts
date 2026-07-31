/**
 * [INPUT]
 * @/store/useChatStore::sendMessage, initializeChat (POS: Active chat state manager)
 * @/store/useWorkspaceStore::addPane (POS: Multi-pane workspace)
 *
 * [OUTPUT]
 * submitLearnMessage: Ensures a chat session exists, then sends raw `/learn` via sendMessage.
 *
 * [POS]
 * Shared learn submission helper for Settings SkillsLearnPanel and slash builtin /learn.
 */

import { buildLearnSlashMessageFromInput } from './composeLearnSlashMessage';

export type SubmitLearnFailureReason = 'no_chat' | 'busy' | 'empty' | 'error';

export interface SubmitLearnMessageOptions {
  /** Full slash input (`/learn …`) or bare learn args. */
  input: string;
}

async function ensureActiveChatId(): Promise<string | null> {
  const { default: useChatStore } = await import('@/store/useChatStore');
  let { chatId } = useChatStore.getState();
  if (chatId?.trim()) return chatId;

  useChatStore.getState().initializeChat(undefined);
  chatId = useChatStore.getState().chatId;
  if (!chatId?.trim()) return null;

  const { default: useWorkspaceStore } = await import('@/store/useWorkspaceStore');
  const panes = useWorkspaceStore.getState().panes;
  const hasPane = panes.some((pane) => pane.chatId === chatId);
  if (!hasPane) {
    useWorkspaceStore.getState().addPane(chatId);
  }

  return chatId;
}

export async function submitLearnMessage(
  options: SubmitLearnMessageOptions,
): Promise<{ ok: true; message: string; chatId: string } | { ok: false; reason: SubmitLearnFailureReason }> {
  const trimmedInput = options.input.trim();
  if (!trimmedInput) {
    return { ok: false, reason: 'empty' };
  }

  const chatId = await ensureActiveChatId();
  if (!chatId) {
    return { ok: false, reason: 'no_chat' };
  }

  const { default: useChatStore } = await import('@/store/useChatStore');
  const { loading, sendMessage } = useChatStore.getState();
  if (loading) {
    return { ok: false, reason: 'busy' };
  }

  const message = buildLearnSlashMessageFromInput(trimmedInput);

  try {
    await sendMessage(message);
    return { ok: true, message, chatId };
  } catch {
    return { ok: false, reason: 'error' };
  }
}
