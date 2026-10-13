/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: Chat state store and message state façade)
 * - @/services/chat::truncateAfterMessage (POS: Chat HTTP API)
 * - @/lib/utils/messageUtils (POS: Message text helpers, explicit skill activation wire format)
 *
 * [OUTPUT]
 * - retryFailedUserMessage: resend a user bubble whose delivery failed, with the attachments it carried.
 * - resendEditedUserMessage: cut the history at an edited user bubble and resend the edited text.
 *
 * [POS]
 * Resend flows of a user bubble. The old bubble is replaced before the new request exists, so a request the agent
 * does not take would take the user's text with it; the text and attachments return to the composer instead.
 */
import {
  buildExplicitSkillWireMessage,
  parseExplicitSkillActivation,
  stripDatetimeTag,
  stripUserMessageDisplayText,
} from '@/lib/utils/messageUtils';
import { truncateAfterMessage } from '@/services/chat';
import { showI18nToast } from '@/services/i18nToastService';
import type { File as ChatFile, Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

/** Give an undelivered request back to the composer, unless the user already started something else there. */
function restoreComposer(chatId: string | undefined, content: string, files: ChatFile[]): void {
  const live = useChatStore.getState();
  const composerInUse =
    live.chatId !== chatId ||
    live.inputMessage.trim() !== '' ||
    live.files.length > 0 ||
    live.pendingExplicitSkillActivation !== null;
  if (composerInUse) {
    return;
  }
  const activation = parseExplicitSkillActivation(content);
  live.setPendingExplicitSkillActivation(
    activation && { skillNames: activation.skillNames, instruction: activation.instruction },
  );
  live.setInputMessage(stripUserMessageDisplayText(content));
  live.setFiles(files);
}

/**
 * Send `content` with exactly the attachments of the bubble it came from: an empty list keeps files that were
 * staged in the composer meanwhile out of this request. A request the agent does not take (refused, busy, failed
 * before the turn) returns to the composer.
 */
async function resend(content: string, files: ChatFile[]): Promise<void> {
  const chatId = useChatStore.getState().chatId;
  try {
    const dispatched = await useChatStore
      .getState()
      .sendMessage(content, undefined, undefined, undefined, undefined, undefined, undefined, undefined, { files });
    if (!dispatched) {
      // The store has already told the user why.
      restoreComposer(chatId, content, files);
    }
  } catch (error) {
    restoreComposer(chatId, content, files);
    if (error instanceof Error && error.name === 'AgentBusyError') {
      showI18nToast('chat.sendBlocked.title', undefined, {
        descriptionKey: 'chat.sendBlocked.busyDescription',
        type: 'warning',
        duration: 3000,
      });
      return;
    }
    console.error('[resend] request failed:', error);
    showI18nToast('chat.messageFailed.title', undefined, {
      descriptionKey: 'chat.messageFailed.generic',
      type: 'error',
      duration: 3000,
    });
  }
}

export function retryFailedUserMessage(message: Message): Promise<void> {
  useChatStore.setState((state) => ({
    messages: state.messages.filter((m) => m.messageId !== message.messageId),
  }));
  return resend(stripDatetimeTag(message.content), message.files ?? []);
}

export async function resendEditedUserMessage(
  chatId: string,
  message: Message,
  messageIndex: number,
  newContent: string,
): Promise<void> {
  const activation = parseExplicitSkillActivation(message.content);
  const content = activation ? buildExplicitSkillWireMessage(activation, newContent) : newContent;

  try {
    await truncateAfterMessage(chatId, message.messageId);
  } catch (error) {
    console.error('Truncate failed:', error);
  }

  useChatStore.setState((state) => ({
    messages: state.messages.slice(0, messageIndex),
  }));
  await resend(content, message.files ?? []);
}
