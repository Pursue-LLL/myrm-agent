/**
 * Test kit for the turn rail, the mobile outline sheet and their jump hook: translation and toast doubles, message and
 * outline builders and fixtures. Imported by the mock factories, so it must not pull in the components.
 */
import { vi } from 'vitest';

import type { TurnOutlineItem } from '@/services/chat';
import type { Message } from '@/store/chat/types';

const hoisted = vi.hoisted(() => ({
  toast: vi.fn<(options: { title: string; variant?: string }) => void>(),
  /** Renders the key, followed by its parameters when it has any, so a test can read both. */
  t: (key: string, params?: Record<string, unknown>) => (params ? `${key} ${JSON.stringify(params)}` : key),
}));
export { hoisted as kit };

export const nextIntlMock = () => ({ useTranslations: () => hoisted.t });

export const toastHookMock = () => ({ toast: hoisted.toast });

export const userMessage = (messageId: string, content: string): Message => ({
  messageId,
  chatId: 'c1',
  role: 'user',
  content,
  createdAt: new Date(0),
});

export const assistantMessage = (messageId: string, content: string): Message => ({
  messageId,
  chatId: 'c1',
  role: 'assistant',
  content,
  createdAt: new Date(0),
});

export const outline = (
  turnIndex: number,
  userMessageId: string,
  promptPreview: string,
  replyPreview: string | null = null,
): TurnOutlineItem => ({
  turn_index: turnIndex,
  user_message_id: userMessageId,
  assistant_message_id: replyPreview === null ? null : `a-${turnIndex}`,
  prompt_preview: promptPreview,
  reply_preview: replyPreview,
  created_at: new Date(0).toISOString(),
  message_count: replyPreview === null ? 1 : 2,
});

/** Three turns in memory: the users' messages sit at indexes 0, 2 and 4. */
export const LOADED_MESSAGES: Message[] = [
  userMessage('u1', 'Hello, help me refactor.'),
  assistantMessage('a1', 'Sure, I will assist with refactoring.'),
  userMessage('u2', 'Step 2: optimize database.'),
  assistantMessage('a2', 'Database indexing applied.'),
  userMessage('u3', 'Step 3: add timeline rail.'),
];

/** The server outline: turns 1-3 are in memory, turn 4 is history that is not loaded. */
export const OUTLINES: TurnOutlineItem[] = [
  outline(1, 'u1', 'Hello, help me refactor.', 'Sure, I will assist with refactoring.'),
  outline(2, 'u2', 'Step 2: optimize database.', 'Database indexing applied.'),
  outline(3, 'u3', 'Step 3: add timeline rail.'),
  outline(4, 'u4-unloaded', 'Step 4: historical turn unloaded.', 'Executed successfully.'),
];

/** Fresh jump callbacks for one test. */
export const jumpHandlers = () => ({
  onJump: vi.fn<(messageIndex: number) => void>(),
  onJumpToMessageId: vi.fn<(messageId: string) => void>(),
  onLoadThroughTurn: vi.fn<(userMessageId: string) => Promise<boolean>>(),
});
