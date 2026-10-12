/**
 * [INPUT]
 * @/store/useChatStore::sendMessage, initializeChat (POS: Active chat state manager)
 * @/store/useWorkspaceStore::addPane (POS: Multi-pane workspace)
 *
 * [OUTPUT]
 * submitLearnMessage: Ensures a chat session exists, then sends raw `/learn` via sendMessage.
 * A send refused before its turn started is reported as `refused` so callers keep the user's input.
 *
 * [POS]
 * Shared learn submission helper for Settings SkillsLearnPanel and slash builtin /learn.
 */

import { buildLearnSlashMessageFromInput } from './composeLearnSlashMessage';

export type SubmitLearnFailureReason = 'no_chat' | 'busy' | 'empty' | 'refused' | 'error';

export interface SubmitLearnMessageOptions {
  /** Full slash input (`/learn …`) or bare learn args. */
  input: string;
}

async function ensureActiveChatId(): Promise<string | null> {
  const { ensureActiveChatId: resolveChatId } = await import('@/lib/chat/ensureActiveChatId');
  return resolveChatId();
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
    // A refused send has already told the user why; reporting success would clear their input and claim a start.
    if (!(await sendMessage(message))) {
      return { ok: false, reason: 'refused' };
    }
    return { ok: true, message, chatId };
  } catch {
    return { ok: false, reason: 'error' };
  }
}
