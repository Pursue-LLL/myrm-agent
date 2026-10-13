/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: Chat state store and message state façade)
 * - @/services/chat::truncateAfterMessage (POS: Chat HTTP API)
 * - @/lib/utils/messageUtils (POS: Message text helpers, explicit skill activation wire format)
 * - @/hooks/message-input/useInputHistory::addInputHistory (POS: Per-agent input history the composer recalls with ArrowUp)
 *
 * [OUTPUT]
 * - retryFailedUserMessage: resend a user bubble whose delivery failed, with the attachments it carried.
 * - resendEditedUserMessage: cut the history at an edited user bubble and resend the edited text.
 *
 * [POS]
 * Resend flows of a user bubble. The old bubble is replaced before the new request exists, so a request the agent
 * does not take would take the user's text with it; the text and attachments return to the composer instead. A
 * composer the user already started stays as it is, and the text goes to the input history like that of a refused
 * direct send. A retry carries the attachments its bubble shows; an edit sends like a normal message, with the
 * composer's own.
 */
import { addInputHistory } from '@/hooks/message-input/useInputHistory';
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
  // Another chat is open now: its composer, agent and incognito state are not those of this request.
  if (live.chatId !== chatId) {
    return;
  }
  const text = stripUserMessageDisplayText(content);
  const composerInUse =
    live.inputMessage.trim() !== '' || live.files.length > 0 || live.pendingExplicitSkillActivation !== null;
  if (composerInUse) {
    // The text stays reachable through the input history, as that of a refused direct send does. An incognito chat
    // persists nothing the user typed.
    if (!live.incognitoMode) {
      addInputHistory(text, live.agentConfig?.agentId);
    }
    return;
  }
  const activation = parseExplicitSkillActivation(content);
  live.setPendingExplicitSkillActivation(
    activation && { skillNames: activation.skillNames, instruction: activation.instruction },
  );
  live.setInputMessage(text);
  live.setFiles(files);
}

/**
 * Send `content`. `attachments` are the files this request carries instead of the composer's: an empty list keeps
 * files staged for the next message out of it, `undefined` lets the request take (and consume) the composer's own
 * like a normal send. A request the agent does not take (refused, busy, failed before the turn) returns to the
 * composer together with the files it carried.
 */
async function resend(content: string, attachments: ChatFile[] | undefined): Promise<void> {
  const live = useChatStore.getState();
  const chatId = live.chatId;
  const sentFiles = attachments ?? live.files;
  try {
    const dispatched = await live.sendMessage(
      content,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      attachments && { files: attachments },
    );
    if (!dispatched) {
      // The store has already told the user why.
      restoreComposer(chatId, content, sentFiles);
    }
  } catch (error) {
    restoreComposer(chatId, content, sentFiles);
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
  await resend(content, undefined);
}
