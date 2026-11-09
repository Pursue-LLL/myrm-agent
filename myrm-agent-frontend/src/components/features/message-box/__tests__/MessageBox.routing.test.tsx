import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import MessageBox from '@/components/features/message-box/MessageBox';
import type { Message } from '@/store/chat/types';

const stableT = (key: string) => key;

const hoisted = vi.hoisted(() => ({
  chatId: 'chat-1' as unknown,
  resend: vi.fn(),
  retry: vi.fn(),
}));

type Props = Record<string, unknown>;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));
vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: Record<string, unknown>) => unknown) => selector({ chatId: hoisted.chatId }),
}));
vi.mock('@/components/features/message-box/useShowSystemMessages', () => ({ useShowSystemMessages: () => false }));
vi.mock('@/components/features/message-box/MarkdownContent', () => ({ default: () => null }));
vi.mock('@/components/features/message-box/userMessageResend', () => ({
  resendEditedUserMessage: hoisted.resend,
  retryFailedUserMessage: hoisted.retry,
}));
vi.mock('@/components/features/message-box/assistant-message/AssistantMessage', () => ({
  AssistantMessage: (props: Props) => (
    <div
      data-testid="assistant"
      data-id={(props.message as Message).messageId}
      data-index={String(props.messageIndex)}
      data-loading={String(props.loading)}
      data-last={String(props.isLast)}
      data-chat={String(props.chatId)}
    />
  ),
}));
vi.mock('@/components/features/message-box/CustomMessageCard', () => ({
  CustomMessageCard: (props: Props) => (
    <div
      data-testid="custom"
      data-type={String(props.customType)}
      data-retention={String(props.retention)}
      data-display={String(props.display)}
      data-details={JSON.stringify(props.details ?? null)}
    >
      {String(props.content)}
    </div>
  ),
}));
vi.mock('@/components/features/message-box/UserMessage', () => ({
  default: (props: Props) => (
    <div
      data-testid="user"
      data-first={String(props.isFirst)}
      data-chat={String(props.chatId)}
      data-editing={String(props.isEditing)}
      data-loading={String(props.isLoading)}
      data-blocked={String(props.continuityBlocked)}
    >
      <button type="button" onClick={props.onEdit as () => void}>
        edit
      </button>
      <button type="button" onClick={() => (props.onEditSubmit as (text: string) => void)('new text')}>
        submit
      </button>
      <button type="button" onClick={props.onCancelEdit as () => void}>
        cancel
      </button>
      {typeof props.onRetry === 'function' && (
        <button type="button" onClick={props.onRetry as () => void}>
          retry
        </button>
      )}
    </div>
  ),
}));

function message(
  role: Message['role'],
  extra: Partial<Message> & { extraData?: Record<string, unknown> } = {},
): Message {
  return {
    messageId: `${role}-1`,
    chatId: 'chat-1',
    role,
    content: `content of ${role}`,
    createdAt: new Date('2026-11-09T00:00:00.000Z'),
    ...extra,
  };
}

function renderRow(target: Message, props: { messageIndex?: number; loading?: boolean; isLast?: boolean } = {}) {
  return render(
    <MessageBox
      message={target}
      messageIndex={props.messageIndex ?? 0}
      loading={props.loading ?? false}
      isLast={props.isLast ?? false}
    />,
  );
}

describe('MessageBox routing', () => {
  beforeEach(() => {
    hoisted.chatId = 'chat-1';
    hoisted.resend.mockReset();
    hoisted.retry.mockReset();
  });

  describe('assistant rows', () => {
    it('hands the message, its position, the streaming flags and the open chat to the assistant bubble', () => {
      renderRow(message('assistant'), { messageIndex: 3, loading: true, isLast: true });

      const bubble = screen.getByTestId('assistant');
      expect(bubble.getAttribute('data-id')).toBe('assistant-1');
      expect(bubble.getAttribute('data-index')).toBe('3');
      expect(bubble.getAttribute('data-loading')).toBe('true');
      expect(bubble.getAttribute('data-last')).toBe('true');
      expect(bubble.getAttribute('data-chat')).toBe('chat-1');
    });

    it('hands over no chat when the store has no usable chat id', () => {
      hoisted.chatId = 42;
      renderRow(message('assistant'));

      expect(screen.getByTestId('assistant').getAttribute('data-chat')).toBe('undefined');
    });
  });

  describe('custom messages', () => {
    it('shows a custom message as a card with defaults for what it leaves out', () => {
      renderRow(message('custom_message'));

      const card = screen.getByTestId('custom');
      expect(card.getAttribute('data-type')).toBe('plugin');
      expect(card.getAttribute('data-retention')).toBe('persistent');
      expect(card.getAttribute('data-display')).toBe('true');
      expect(card.textContent).toBe('content of custom_message');
      expect(screen.queryByTestId('assistant')).toBeNull();
    });

    it('takes the card settings from the extra data of the message', () => {
      renderRow(
        message('custom_message', {
          extraData: { custom_type: 'notice', retention: 'ephemeral', details: { a: 1 } },
        }),
      );

      const card = screen.getByTestId('custom');
      expect(card.getAttribute('data-type')).toBe('notice');
      expect(card.getAttribute('data-retention')).toBe('ephemeral');
      expect(card.getAttribute('data-details')).toBe('{"a":1}');
    });

    it('shows nothing for a custom message that asks not to be displayed', () => {
      const { container } = renderRow(message('custom_message', { extraData: { display: false } }));

      expect(container.innerHTML).toBe('');
    });

    it.each(['assistant', 'user'] as const)('treats a %s row flagged as a custom message as a card', (role) => {
      renderRow(message(role, { extraData: { is_custom_message: true } }));

      expect(screen.getByTestId('custom')).toBeTruthy();
      expect(screen.queryByTestId('assistant')).toBeNull();
      expect(screen.queryByTestId('user')).toBeNull();
    });

    it('does not treat a row as a custom message when the flag is false', () => {
      renderRow(message('assistant', { extraData: { is_custom_message: false } }));

      expect(screen.getByTestId('assistant')).toBeTruthy();
    });
  });

  describe('user rows', () => {
    it('marks only the first row as first and passes the loading state on', () => {
      const { unmount } = renderRow(message('user'), { messageIndex: 0, loading: true });
      expect(screen.getByTestId('user').getAttribute('data-first')).toBe('true');
      expect(screen.getByTestId('user').getAttribute('data-loading')).toBe('true');
      expect(screen.getByTestId('user').getAttribute('data-blocked')).toBe('true');
      unmount();

      renderRow(message('user'), { messageIndex: 2 });
      expect(screen.getByTestId('user').getAttribute('data-first')).toBe('false');
      expect(screen.getByTestId('user').getAttribute('data-loading')).toBe('false');
    });

    it('offers a retry only for a message that failed to send, and retries that message', () => {
      const { unmount } = renderRow(message('user'));
      expect(screen.queryByText('retry')).toBeNull();
      unmount();

      const failed = message('user', { sendFailed: true });
      renderRow(failed);
      fireEvent.click(screen.getByText('retry'));
      expect(hoisted.retry).toHaveBeenCalledWith(failed);
    });

    it('enters and leaves the edit mode of this row', () => {
      renderRow(message('user'));
      expect(screen.getByTestId('user').getAttribute('data-editing')).toBe('false');

      fireEvent.click(screen.getByText('edit'));
      expect(screen.getByTestId('user').getAttribute('data-editing')).toBe('true');

      fireEvent.click(screen.getByText('cancel'));
      expect(screen.getByTestId('user').getAttribute('data-editing')).toBe('false');
    });

    it('resends the edited text in the open chat and leaves the edit mode', () => {
      const target = message('user');
      renderRow(target);

      fireEvent.click(screen.getByText('edit'));
      fireEvent.click(screen.getByText('submit'));

      expect(hoisted.resend).toHaveBeenCalledWith('chat-1', target, 'new text');
      expect(screen.getByTestId('user').getAttribute('data-editing')).toBe('false');
    });

    it('keeps the edit open and sends nothing while an answer is loading', () => {
      renderRow(message('user'), { loading: true });

      fireEvent.click(screen.getByText('edit'));
      fireEvent.click(screen.getByText('submit'));

      expect(hoisted.resend).not.toHaveBeenCalled();
      expect(screen.getByTestId('user').getAttribute('data-editing')).toBe('true');
    });

    it('keeps the edit open and sends nothing without an open chat', () => {
      hoisted.chatId = undefined;
      renderRow(message('user'));

      fireEvent.click(screen.getByText('edit'));
      fireEvent.click(screen.getByText('submit'));

      expect(hoisted.resend).not.toHaveBeenCalled();
      expect(screen.getByTestId('user').getAttribute('data-editing')).toBe('true');
    });
  });
});
