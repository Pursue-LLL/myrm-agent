/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager of the visible chat session)
 * - @/services/chat::truncateAfterMessage (POS: Chat HTTP API, history truncation)
 * - @/services/i18nToastService::showI18nToast (POS: Translated toasts outside React components)
 * - @/lib/utils/messageUtils (POS: Message text cleanup helpers, explicit skill activation wire format)
 * - @/hooks/message-input/useInputHistory::addInputHistory (POS: Per-agent input history the composer recalls with ArrowUp)
 *
 * [OUTPUT]
 * - retryFailedUserMessage: resend a user bubble whose delivery failed, with the attachments it carried.
 * - resendEditedUserMessage: cut the history at an edited user bubble and resend the edited text.
 *
 * [POS]
 * Resend flows of a user bubble. The old bubble is replaced before the new request exists, so a request the agent
 * does not take would take the user's text with it; the text and attachments return to the composer instead. When
 * the composer cannot take them (the user started the next message or opened another chat), the text goes to the
 * input history of the chat it came from, like that of a refused direct send. A retry carries the attachments its
 * bubble shows; an edit sends like a normal message, with the composer's own, and is dropped with a notice when its
 * chat is left while the server cuts the history.
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

/**
 * The chat a resend belongs to, read before anything awaits: the chat store always holds whichever chat is open,
 * so by the time a request settles its chat, agent and incognito state may be another one's.
 */
interface Origin {
  chatId: string | undefined;
  agentId: string | undefined;
  incognito: boolean;
}

function readOrigin(): Origin {
  const { chatId, agentConfig, incognitoMode } = useChatStore.getState();
  return { chatId, agentId: agentConfig?.agentId, incognito: incognitoMode };
}

/** Keep text the composer cannot take reachable through the input history. An incognito chat persists none. */
function keepInInputHistory(origin: Origin, text: string): void {
  if (!origin.incognito) {
    addInputHistory(text, origin.agentId);
  }
}

function notifyNotSent(): void {
  showI18nToast('chat.messageFailed.title', undefined, {
    descriptionKey: 'chat.messageFailed.generic',
    type: 'error',
    duration: 3000,
  });
}

/** Give an undelivered request back to the composer, unless the user already started something else there. */
function restoreComposer(origin: Origin, content: string, files: ChatFile[]): void {
  const live = useChatStore.getState();
  const text = stripUserMessageDisplayText(content);
  const composerFree =
    live.chatId === origin.chatId &&
    live.inputMessage.trim() === '' &&
    live.files.length === 0 &&
    live.pendingExplicitSkillActivation === null;
  if (!composerFree) {
    keepInInputHistory(origin, text);
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
async function resend(origin: Origin, content: string, attachments: ChatFile[] | undefined): Promise<void> {
  const live = useChatStore.getState();
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
      restoreComposer(origin, content, sentFiles);
    }
  } catch (error) {
    restoreComposer(origin, content, sentFiles);
    if (error instanceof Error && error.name === 'AgentBusyError') {
      showI18nToast('chat.sendBlocked.title', undefined, {
        descriptionKey: 'chat.sendBlocked.busyDescription',
        type: 'warning',
        duration: 3000,
      });
      return;
    }
    console.error('[resend] request failed:', error);
    notifyNotSent();
  }
}

export function retryFailedUserMessage(message: Message): Promise<void> {
  const origin = readOrigin();
  useChatStore.setState((state) => ({
    messages: state.messages.filter((m) => m.messageId !== message.messageId),
  }));
  return resend(origin, stripDatetimeTag(message.content), message.files ?? []);
}

export async function resendEditedUserMessage(
  chatId: string,
  message: Message,
  messageIndex: number,
  newContent: string,
): Promise<void> {
  const origin = readOrigin();
  const activation = parseExplicitSkillActivation(message.content);
  const content = activation ? buildExplicitSkillWireMessage(activation, newContent) : newContent;

  try {
    await truncateAfterMessage(chatId, message.messageId);
  } catch (error) {
    console.error('Truncate failed:', error);
  }

  // The open chat is not the one that was cut: the edit has no transcript to join, and the open chat must neither
  // lose its messages nor receive this request.
  if (useChatStore.getState().chatId !== chatId) {
    keepInInputHistory(origin, newContent);
    notifyNotSent();
    return;
  }

  useChatStore.setState((state) => ({
    messages: state.messages.slice(0, messageIndex),
  }));
  await resend(origin, content, undefined);
}
