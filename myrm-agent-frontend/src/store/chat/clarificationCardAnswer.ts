/**
 * [INPUT]
 * - @/store/useChatStore (POS: the clarification card lives on an assistant row of the message list)
 * - ./streamErrors::ApprovalExpiredError (POS: the timeout already settled the card, so the answer is not undone)
 * - ./clarificationCardDraft (POS: the user's unsent input, kept only for a card that is about to reopen)
 * - ./hitlAnswerRecord::clarificationAnswerAsText (POS: the late answer as a sendable message)
 *
 * [OUTPUT]
 * - settleClarificationCard: mark the card answered and keep how it was answered
 * - answerClarificationWithResume: close the card, send the resumed answer, reopen the card if the server never took it,
 *   hand the answer to the composer if the timeout got there first
 *
 * [POS]
 * Answer flow of the clarification card. A resume request streams the whole resumed run, and the composer stays taken
 * over until the card's row says answered, so the card closes as soon as the request is sent.
 */

import useChatStore from '@/store/useChatStore';

import { clearClarificationDraft, saveClarificationDraft, type ClarificationDraft } from './clarificationCardDraft';
import { clarificationAnswerAsText } from './hitlAnswerRecord';
import { ApprovalExpiredError } from './streamErrors';
import type { HitlAnswerRecord, Message } from './types';

type ClarificationCard = NonNullable<Message['clarification']>;

const cardRow = (messages: Message[], messageId: string) =>
  messages.find((m) => m.messageId === messageId && m.role === 'assistant');

const findCard = (messageId: string) => cardRow(useChatStore.getState().messages, messageId)?.clarification;

// The value the server resumes with when its timeout settles the card, and persists in the same record.
const timeoutRecord = (): HitlAnswerRecord => ({ by: 'timeout', value: {} });

function updateCard(messageId: string, apply: (card: ClarificationCard) => void): void {
  useChatStore.setState((state) => {
    const card = cardRow(state.messages, messageId)?.clarification;
    if (card) {
      apply(card);
    }
  });
}

export function settleClarificationCard(messageId: string, record: HitlAnswerRecord): void {
  updateCard(messageId, (card) => {
    card.answered = true;
    card.answerRecord = record;
  });
}

// Appends, so whatever the user already typed in the composer survives.
function handBackToComposer(text: string): void {
  if (!text) {
    return;
  }
  const { inputMessage, setInputMessage } = useChatStore.getState();
  setInputMessage(inputMessage.trim() ? `${inputMessage.trimEnd()}\n\n${text}` : text);
}

function reopenClarificationCard(messageId: string): void {
  updateCard(messageId, (card) => {
    card.answered = false;
    delete card.answerRecord;
  });
}

/**
 * Rethrows whatever `sendResume` throws so the caller reports it. A card the resumed run has replaced or settled since
 * is left alone: only the exact card closed here is reopened or rewritten.
 * - Refused resume: the card comes back carrying what the user wrote (`draft`).
 * - Timeout already settled the turn: the card stays closed and shows the timeout, and the answer that came too late
 *   goes to the composer so it can still be sent as a message.
 * A draft only exists while the card is waiting to be reopened, so a card chained after a successful answer starts empty.
 */
export async function answerClarificationWithResume(
  messageId: string,
  answer: { value: unknown; draft: ClarificationDraft },
  sendResume: () => Promise<unknown>,
): Promise<void> {
  clearClarificationDraft(messageId);
  settleClarificationCard(messageId, { by: 'user', value: answer.value });
  const closedCard = findCard(messageId);
  const isStillClosedCard = () => closedCard !== undefined && findCard(messageId) === closedCard;
  try {
    await sendResume();
  } catch (error) {
    if (error instanceof ApprovalExpiredError) {
      handBackToComposer(clarificationAnswerAsText(answer.value, closedCard?.form));
      if (isStillClosedCard()) {
        settleClarificationCard(messageId, timeoutRecord());
      }
    } else if (isStillClosedCard()) {
      saveClarificationDraft(messageId, answer.draft);
      reopenClarificationCard(messageId);
    }
    throw error;
  }
}
