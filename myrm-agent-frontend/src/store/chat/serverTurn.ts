/**
 * [INPUT]
 * @/services/chat::cancelActiveChatAgent (POS: chat-level Stop endpoint)
 * @/services/i18nToastService::showI18nToast (POS: Stop result feedback)
 * ./types::ChatState (POS: chat id and the server-reported session statuses)
 *
 * [OUTPUT]
 * selectChatGenerating: whether the server reports a turn running in the open chat
 * cancelChatTurn: stop the turn running in a chat by chat id and report the result
 *
 * [POS]
 * A turn the server starts by itself (a wake after background work finishes) has no AbortController in this client.
 * The server-reported session status is the only signal that it runs, and the chat-level cancel the only handle that stops it.
 */

import { cancelActiveChatAgent } from '@/services/chat';
import { showI18nToast } from '@/services/i18nToastService';
import type { ChatState } from './types';

export const selectChatGenerating = ({
  chatId,
  sessionStatuses,
}: Pick<ChatState, 'chatId' | 'sessionStatuses'>): boolean => !!chatId && sessionStatuses[chatId] === 'generating';

export async function cancelChatTurn(chatId: string): Promise<void> {
  try {
    await cancelActiveChatAgent(chatId);
    showI18nToast('agent.mobileCommand.stopTaskSuccess', undefined, { type: 'success' });
  } catch {
    showI18nToast('agent.mobileCommand.stopTaskFailed', undefined, { type: 'warning' });
  }
}
