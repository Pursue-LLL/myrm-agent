/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager of the visible chat session)
 * - @/lib/api::ApiError (POS: Typed API failure carrying the HTTP status of a rejected request)
 * - @/services/chat::truncateAfterMessage (POS: Chat HTTP API, history truncation)
 * - @/services/i18nToastService::showI18nToast (POS: Translated toasts outside React components)
 * - @/lib/utils/messageUtils (POS: Message text cleanup helpers, explicit skill activation wire format)
 * - @/hooks/message-input/useInputHistory::addInputHistory (POS: Per-agent input history recalled with ArrowUp)
 *
 * [OUTPUT]
 * - readSendOrigin: the chat a send belongs to, read before anything awaits.
 * - retryFailedUserMessage: resend a user bubble whose delivery failed, with the attachments it carried.
 * - resendEditedUserMessage: cut the history at an edited user bubble and resend the edited text.
 * - sendGoalReviewFeedback: send the feedback of a rejected goal review as the next message of the chat it was
 *   written in.
 *
 * [POS]
 * Flows that send text through the chat store outside the composer: retry of a failed send, edit-and-resend, and the
 * feedback of a rejected goal review. A request the agent does not take returns to the composer (or to the input
 * history of its chat) instead of vanishing with the replaced bubble or the closed panel, and an edit replaces the
 * transcript only after the server cut the history.
 */
import { addInputHistory } from '@/hooks/message-input/useInputHistory';
import { ApiError } from '@/lib/api';
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
 * The chat a send belongs to, read before anything awaits: the chat store always holds whichever chat is open,
 * so by the time a request settles its chat, agent and incognito state may be another one's.
 */
export interface SendOrigin {
  chatId: string | undefined;
  agentId: string | undefined;
  incognito: boolean;
}

export function readSendOrigin(): SendOrigin {
  const { chatId, agentConfig, incognitoMode } = useChatStore.getState();
  return { chatId, agentId: agentConfig?.agentId, incognito: incognitoMode };
}

/** Keep text the composer cannot take reachable through the input history. An incognito chat persists none. */
function keepInInputHistory(origin: SendOrigin, text: string): void {
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

/** Warn that the request was held back because another one is still in progress. */
function notifySendBlocked(
  descriptionKey: 'chat.sendBlocked.busyDescription' | 'chat.sendBlocked.processingDescription',
): void {
  showI18nToast('chat.sendBlocked.title', undefined, { descriptionKey, type: 'warning', duration: 3000 });
}

/** Give an undelivered request back to the composer, unless the user already started something else there. */
function restoreComposer(origin: SendOrigin, content: string, files: ChatFile[]): void {
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
async function resend(origin: SendOrigin, content: string, attachments: ChatFile[] | undefined): Promise<void> {
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
      notifySendBlocked('chat.sendBlocked.busyDescription');
      return;
    }
    console.error('[resend] request failed:', error);
    notifyNotSent();
  }
}

export function retryFailedUserMessage(message: Message): Promise<void> {
  const origin = readSendOrigin();
  useChatStore.setState((state) => ({
    messages: state.messages.filter((m) => m.messageId !== message.messageId),
  }));
  return resend(origin, stripDatetimeTag(message.content), message.files ?? []);
}

/**
 * The chats with an edit running, from its server cut until its request settled. The editor closes on submit, so the
 * user can submit another edit while the first still waits on the server, and two cuts at different bubbles would
 * race over the same transcript. Another chat has a transcript of its own, and the turn of the first may run for
 * minutes, so only the chat of the running edit is held back.
 */
const chatsWithEditInFlight = new Set<string>();

/**
 * Cut the stored history at `messageId`; resolves whether the edit may go on. It may when the history was cut and
 * when the server holds nothing to cut at that bubble (a chat it does not store answers 404, a message it does not
 * hold answers `success: false`). Any other failure would leave the old turns in the agent's context.
 */
async function cutHistoryAt(chatId: string, messageId: string): Promise<boolean> {
  try {
    await truncateAfterMessage(chatId, messageId);
    return true;
  } catch (error) {
    if (error instanceof ApiError && error.code === 404) {
      return true;
    }
    console.error('[resend] history cut failed:', error);
    return false;
  }
}

/** Give up a send that cannot go ahead: its text returns to the user instead of vanishing with the old bubble. */
function abandonSend(origin: SendOrigin, content: string): void {
  restoreComposer(origin, content, []);
  notifyNotSent();
}

/**
 * Send the feedback of a rejected goal review as the next user message of the chat the review belongs to. The goal is
 * active again by then (the agent reads only an active goal), and the review panel is gone, so a feedback the agent
 * does not take returns to the composer like any other undelivered request. Files staged in the composer are the
 * user's next message, so this one neither carries nor consumes them.
 */
export async function sendGoalReviewFeedback(origin: SendOrigin, feedback: string): Promise<void> {
  if (useChatStore.getState().chatId !== origin.chatId) {
    abandonSend(origin, feedback);
    return;
  }
  await resend(origin, feedback, []);
}

/**
 * Replace the history from the edited bubble on with the edited text. The server is cut first, so the agent never
 * sees the old turns next to their replacement; an edit that cannot go ahead leaves the transcript as it was.
 */
export async function resendEditedUserMessage(chatId: string, message: Message, newContent: string): Promise<void> {
  const origin = readSendOrigin();
  const activation = parseExplicitSkillActivation(message.content);
  const content = activation ? buildExplicitSkillWireMessage(activation, newContent) : newContent;

  if (chatsWithEditInFlight.has(chatId) || useChatStore.getState().loading) {
    restoreComposer(origin, content, []);
    notifySendBlocked('chat.sendBlocked.processingDescription');
    return;
  }

  chatsWithEditInFlight.add(chatId);
  try {
    if (!(await cutHistoryAt(chatId, message.messageId))) {
      abandonSend(origin, content);
      return;
    }

    // The transcript has to follow the cut, but only where it still matches: the open chat may be another one by
    // now, a turn may have started (its bubbles must not be cut away), and older messages may have been loaded above
    // the edited bubble (the index it had when the user clicked is stale).
    const live = useChatStore.getState();
    const anchor = live.messages.findIndex((m) => m.messageId === message.messageId);
    if (live.chatId !== chatId || live.loading || anchor < 0) {
      abandonSend(origin, content);
      return;
    }

    useChatStore.setState({ messages: live.messages.slice(0, anchor) });
    await resend(origin, content, undefined);
  } finally {
    chatsWithEditInFlight.delete(chatId);
  }
}
