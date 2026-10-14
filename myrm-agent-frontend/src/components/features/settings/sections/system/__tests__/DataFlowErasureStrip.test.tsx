import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DataFlowErasureStrip } from '../DataFlowErasureStrip';
import { ConversationPurgeBusyError } from '@/services/conversationPurge';
import useChatStore from '@/store/useChatStore';
import type { ChatHistoryItem, PaginationInfo } from '@/store/chat/types/messages';

type Translate = (key: string, values?: Record<string, unknown>) => string;

// Stable per-namespace reference: a new function per render would re-create every callback that lists `t` as a dependency.
const { mockPurge, mockToastError, translatorFor } = vi.hoisted(() => {
  const translators = new Map<string, Translate>();
  return {
    mockPurge: vi.fn(),
    mockToastError: vi.fn(),
    translatorFor: (namespace: string): Translate => {
      const existing = translators.get(namespace);
      if (existing) {
        return existing;
      }
      const translate: Translate = (key, values) =>
        values ? `${namespace}.${key}:${JSON.stringify(values)}` : `${namespace}.${key}`;
      translators.set(namespace, translate);
      return translate;
    },
  };
});

vi.mock('next-intl', () => ({ useTranslations: translatorFor }));

vi.mock('@/lib/utils/toast', () => ({
  toast: { success: vi.fn(), error: mockToastError },
}));

vi.mock('@/services/conversationPurge', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/conversationPurge')>()),
  purgeAllConversations: mockPurge,
}));

const DIALOG = 'settings.securityPolicy.dataFlow';
const OPEN_BUTTON = `${DIALOG}.eraseButton`;

const historyItem: ChatHistoryItem = {
  id: 'chat-1',
  title: 'Old chat',
  firstMessage: 'hello',
  lastMessage: 'bye',
  actionMode: 'chat',
  source: 'web',
  updatedAt: new Date(0),
  createdAt: new Date(0),
};

const pagination: PaginationInfo = {
  page: 1,
  page_size: 20,
  total: 1,
  total_pages: 1,
  has_next: false,
  has_prev: false,
};

const openDialog = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(screen.getByRole('button', { name: OPEN_BUTTON }));
  return screen.findByTestId('confirm-dialog-confirm');
};

describe('DataFlowErasureStrip', () => {
  const assign = vi.fn();

  beforeEach(() => {
    mockPurge.mockReset();
    mockToastError.mockReset();
    assign.mockReset();
    vi.stubGlobal('location', { ...window.location, assign });
    useChatStore.setState({ chatHistoryItems: [historyItem], chatHistoryPagination: pagination });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('describes what is erased and what is kept before any click', () => {
    render(<DataFlowErasureStrip />);
    expect(screen.getByText(`${DIALOG}.eraseTitle`)).toBeInTheDocument();
    expect(screen.getByText(`${DIALOG}.eraseDesc`)).toBeInTheDocument();
    expect(mockPurge).not.toHaveBeenCalled();
  });

  it('does not purge when the confirmation is cancelled', async () => {
    const user = userEvent.setup();
    render(<DataFlowErasureStrip />);
    await openDialog(user);
    expect(screen.getByText(`${DIALOG}.eraseConfirmDesc`)).toBeInTheDocument();

    await user.click(screen.getByTestId('confirm-dialog-cancel'));

    expect(mockPurge).not.toHaveBeenCalled();
    expect(useChatStore.getState().chatHistoryItems).toEqual([historyItem]);
  });

  it('purges once, empties the sidebar cache and offers a fresh start on success', async () => {
    mockPurge.mockResolvedValue({ purged_chats: 3, purged_messages: 12, cleared_sandboxes: 3 });
    const user = userEvent.setup();
    render(<DataFlowErasureStrip />);

    await user.click(await openDialog(user));

    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent(`${DIALOG}.eraseSuccess:{"count":3}`);
    expect(mockPurge).toHaveBeenCalledTimes(1);
    expect(useChatStore.getState().chatHistoryItems).toEqual([]);
    expect(useChatStore.getState().chatHistoryPagination).toBeNull();
    expect(screen.queryByRole('button', { name: OPEN_BUTTON })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: `${DIALOG}.eraseStartFresh` }));
    expect(assign).toHaveBeenCalledWith('/');
  });

  it('tells the user to stop the running conversation and keeps their chats', async () => {
    mockPurge.mockRejectedValue(new ConversationPurgeBusyError());
    const user = userEvent.setup();
    render(<DataFlowErasureStrip />);

    await user.click(await openDialog(user));

    await waitFor(() => expect(mockToastError).toHaveBeenCalledWith(`${DIALOG}.eraseBusy`));
    expect(useChatStore.getState().chatHistoryItems).toEqual([historyItem]);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: OPEN_BUTTON })).toBeInTheDocument();
  });

  it('shows a retryable message for any other failure and keeps their chats', async () => {
    mockPurge.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<DataFlowErasureStrip />);

    await user.click(await openDialog(user));

    await waitFor(() => expect(mockToastError).toHaveBeenCalledWith(`${DIALOG}.eraseFailed`));
    expect(useChatStore.getState().chatHistoryItems).toEqual([historyItem]);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: OPEN_BUTTON })).toBeInTheDocument();
  });
});
