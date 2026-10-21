/**
 * Shared fixtures for the resend tests: a chat holding one answered turn plus the user bubble 'r-2' whose send
 * failed, a stubbed `sendMessage`, and readers for what a user can see (transcript, composer).
 * The importing test file mocks the two collaborators `resetResendWorld` clears: the input history and the toasts.
 */
import { vi } from 'vitest';
import { addInputHistory } from '@/hooks/message-input/useInputHistory';
import { showI18nToast } from '@/services/i18nToastService';
import type { ChatState, File as ChatFile, Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

export const CHAT_ID = 'chat-resend';

export const REPORT_PDF: ChatFile = {
  id: 'f-report',
  fileName: 'report.pdf',
  fileExtension: 'pdf',
  fileType: 'uploaded',
  fileUrl: 'https://files.test/f-report',
};

export const STAGED_PNG: ChatFile = {
  id: 'f-staged',
  fileName: 'staged.png',
  fileExtension: 'png',
  fileType: 'uploaded',
  fileUrl: 'https://files.test/f-staged',
};

export function bubble(
  role: Message['role'],
  messageId: string,
  content: string,
  extra: Partial<Message> = {},
): Message {
  return { messageId, chatId: CHAT_ID, role, content, createdAt: new Date(), ...extra } as Message;
}

export const failedBubble = bubble(
  'user',
  'r-2',
  'summarize the report\n<current_datetime>2026-10-13</current_datetime>',
  {
    sendFailed: true,
    files: [REPORT_PDF],
  },
);

export const sendMessage = vi.fn<ChatState['sendMessage']>();
const SENT_CONTENT = 0;
const SENT_ATTACHMENTS = 8;

export const sentRequest = () => {
  const call = sendMessage.mock.calls[0];
  return { content: call[SENT_CONTENT], attachments: call[SENT_ATTACHMENTS] };
};
export const transcript = () => useChatStore.getState().messages.map((m) => m.messageId);
export const composer = () => {
  const { inputMessage, files, pendingExplicitSkillActivation } = useChatStore.getState();
  return { inputMessage, files, pendingExplicitSkillActivation };
};
export const agentConfig = (agentId: string) => ({ agentId }) as NonNullable<ChatState['agentConfig']>;

export function resetResendWorld(): void {
  sendMessage.mockReset();
  sendMessage.mockResolvedValue(true);
  vi.mocked(showI18nToast).mockReset();
  vi.mocked(addInputHistory).mockReset();
  vi.spyOn(console, 'error').mockImplementation(() => {});
  useChatStore.setState({
    chatId: CHAT_ID,
    messages: [bubble('user', 'r-1', 'hello'), bubble('assistant', 'r-1', 'hi there'), failedBubble],
    loading: false,
    inputMessage: '',
    files: [],
    pendingExplicitSkillActivation: null,
    incognitoMode: false,
    agentConfig: null,
    sendMessage,
  });
}
