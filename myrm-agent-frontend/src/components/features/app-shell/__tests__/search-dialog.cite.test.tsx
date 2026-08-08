/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SearchDialog } from '../search-dialog';
import type { SearchResult } from '@/services/chat';

const mockPush = vi.hoisted(() => vi.fn());
const mockSearchChatHistory = vi.hoisted(() => vi.fn());
const mockAddMentionReference = vi.hoisted(() => vi.fn());
const mockToastInfo = vi.hoisted(() => vi.fn());
const mockOnOpenChange = vi.hoisted(() => vi.fn());

const mockChatState = vi.hoisted(() => ({
  chatId: 'current-chat-id',
  addMentionReference: mockAddMentionReference,
}));

const mockSonnerToast = vi.hoisted(() => {
  const fn = vi.fn();
  return Object.assign(fn, {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: (...args: unknown[]) => mockToastInfo(...args),
    promise: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
    message: vi.fn(),
  });
});

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('sonner', () => ({
  toast: mockSonnerToast,
}));

vi.mock('@/services/chat', () => ({
  searchChatHistory: (...args: unknown[]) => mockSearchChatHistory(...args),
}));

vi.mock('@/store/useChatStore', () => ({
  default: Object.assign(
    (selector: (state: typeof mockChatState) => unknown) => selector(mockChatState),
    { getState: () => mockChatState },
  ),
}));

const searchItem: SearchResult = {
  id: '42',
  chat_id: 'current-chat-id',
  chat_title: 'Current chat',
  role: 'assistant',
  content: 'matched content',
  snippet: 'matched snippet',
  sent_at: '2026-08-04T10:00:00.000Z',
};

const otherChatItem: SearchResult = {
  ...searchItem,
  id: '43',
  chat_id: 'other-chat-id',
  chat_title: 'Other chat',
};

describe('SearchDialog cite to composer', () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockSearchChatHistory.mockReset();
    mockAddMentionReference.mockReset();
    mockToastInfo.mockReset();
    mockOnOpenChange.mockReset();
    mockChatState.chatId = 'current-chat-id';
    mockSearchChatHistory.mockResolvedValue({ items: [searchItem], total: 1 });
  });

  it('shows info toast when citing a result from the current chat', async () => {
    render(
      <SearchDialog open onOpenChange={mockOnOpenChange}>
        <div />
      </SearchDialog>,
    );

    const input = await screen.findByPlaceholderText('search.placeholder');
    fireEvent.change(input, { target: { value: 'hello' } });

    await waitFor(() => {
      expect(mockSearchChatHistory).toHaveBeenCalledWith('hello', 20, 0, undefined, undefined);
    });

    const citeButtons = screen.getAllByRole('button', { name: 'search.citeToComposer' });
    fireEvent.click(citeButtons[0]!);

    expect(mockToastInfo).toHaveBeenCalledWith('search.citeSameChat');
    expect(mockAddMentionReference).not.toHaveBeenCalled();
    expect(mockOnOpenChange).toHaveBeenCalledWith(false);
  });

  it('adds prior_chat mention when citing a result from another chat', async () => {
    mockSearchChatHistory.mockResolvedValue({ items: [otherChatItem], total: 1 });

    render(
      <SearchDialog open onOpenChange={mockOnOpenChange}>
        <div />
      </SearchDialog>,
    );

    const input = await screen.findByPlaceholderText('search.placeholder');
    fireEvent.change(input, { target: { value: 'hello' } });

    await waitFor(() => {
      expect(mockSearchChatHistory).toHaveBeenCalled();
    });

    const citeButtons = screen.getAllByRole('button', { name: 'search.citeToComposer' });
    fireEvent.click(citeButtons[0]!);

    expect(mockToastInfo).not.toHaveBeenCalled();
    expect(mockAddMentionReference).toHaveBeenCalledWith({
      type: 'prior_chat',
      label: '@chat:Other chat',
      path: 'other-chat-id',
      fileId: 'other-chat-id',
      source: 'special',
      size: null,
    });
    expect(mockOnOpenChange).toHaveBeenCalledWith(false);
  });
});
