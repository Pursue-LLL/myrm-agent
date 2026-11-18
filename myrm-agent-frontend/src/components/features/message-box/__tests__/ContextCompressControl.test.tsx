import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { COMPACT_FOCUS_TOPIC_MAX_LENGTH } from '@/lib/constants/compact-focus-topic';
import { deferred } from '@/test-utils/deferred';
import { ContextCompressControl } from '../ContextCompressControl';

const translate = vi.hoisted(() => (key: string, params?: Record<string, unknown>) => {
  if (params) {
    return `${key}:${JSON.stringify(params)}`;
  }
  return key;
});
const mockCompactChat = vi.hoisted(() => vi.fn());
const mockRefreshCompactionState = vi.hoisted(() => vi.fn());

vi.mock('next-intl', () => ({
  useTranslations: () => translate,
}));

vi.mock('@/services/chat', () => ({
  compactChat: mockCompactChat,
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => ({ refreshCompactionState: mockRefreshCompactionState }),
  },
}));

function renderControl({ chatId = 'chat-1' as string | null, usagePercent = 50 } = {}) {
  render(<ContextCompressControl chatId={chatId} usagePercent={usagePercent} />);
}

const compressButton = () => screen.getByRole('button', { name: /^compress/ });

describe('ContextCompressControl', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRefreshCompactionState.mockResolvedValue(undefined);
  });

  it.each([
    { usagePercent: 29.9, chatId: 'chat-1', enabled: false },
    { usagePercent: 30, chatId: 'chat-1', enabled: true },
    { usagePercent: 80, chatId: null, enabled: false },
  ])('usage $usagePercent with chat $chatId enables the button: $enabled', ({ usagePercent, chatId, enabled }) => {
    renderControl({ chatId, usagePercent });

    expect(compressButton().hasAttribute('disabled')).toBe(!enabled);
  });

  it('compresses without a topic, reports the saved tokens and hands the compaction to the store', async () => {
    mockCompactChat.mockResolvedValue({ compacted: true, tokens_saved: 15200, backup_path: '/tmp/backup.json' });
    renderControl();

    await userEvent.setup().click(compressButton());

    expect(await screen.findByText('compressSuccess:{"tokens":"15.2K"}')).toBeInTheDocument();
    expect(mockCompactChat).toHaveBeenCalledWith('chat-1', undefined);
    expect(mockRefreshCompactionState).toHaveBeenCalledWith('chat-1', {
      tokensSaved: 15200,
      snapshotPath: '/tmp/backup.json',
    });
  });

  it('records no snapshot path when the server kept no backup', async () => {
    mockCompactChat.mockResolvedValue({ compacted: true, tokens_saved: 900, backup_path: null });
    renderControl();

    await userEvent.setup().click(compressButton());

    await waitFor(() => {
      expect(mockRefreshCompactionState).toHaveBeenCalledWith('chat-1', { tokensSaved: 900, snapshotPath: undefined });
    });
  });

  it.each([
    { name: 'trims the typed focus topic', typed: '  auth module  ', sent: 'auth module' },
    { name: 'sends no focus topic for blank input', typed: '   ', sent: undefined },
  ])('$name', async ({ typed, sent }) => {
    mockCompactChat.mockResolvedValue({ compacted: true, tokens_saved: 12000 });
    renderControl();
    const user = userEvent.setup();

    await user.type(screen.getByPlaceholderText('focusHintPlaceholder'), typed);
    await user.click(compressButton());

    await waitFor(() => {
      expect(mockCompactChat).toHaveBeenCalledWith('chat-1', sent);
    });
  });

  it('stops typing and pasting the focus topic at the characters the server accepts', () => {
    renderControl();

    expect(screen.getByPlaceholderText('focusHintPlaceholder')).toHaveAttribute(
      'maxlength',
      String(COMPACT_FOCUS_TOPIC_MAX_LENGTH),
    );
  });

  it('says nothing needed compressing and leaves the store alone', async () => {
    mockCompactChat.mockResolvedValue({ compacted: false, tokens_saved: 0 });
    renderControl();

    await userEvent.setup().click(compressButton());

    expect(await screen.findByText('compressNotNeeded')).toBeInTheDocument();
    expect(mockRefreshCompactionState).not.toHaveBeenCalled();
  });

  it.each([
    { rejection: new Error('Server error'), shown: 'Server error' },
    { rejection: 'offline', shown: 'compressError' },
  ])('shows $shown when the request fails and leaves the store alone', async ({ rejection, shown }) => {
    mockCompactChat.mockRejectedValue(rejection);
    renderControl();

    await userEvent.setup().click(compressButton());

    expect(await screen.findByText(shown)).toBeInTheDocument();
    expect(mockRefreshCompactionState).not.toHaveBeenCalled();
  });

  it('shows a busy button and drops the previous outcome while a new request runs', async () => {
    mockCompactChat.mockResolvedValueOnce({ compacted: false, tokens_saved: 0 });
    renderControl();
    const user = userEvent.setup();
    await user.click(compressButton());
    expect(await screen.findByText('compressNotNeeded')).toBeInTheDocument();

    const pending = deferred<{ compacted: boolean; tokens_saved: number }>();
    mockCompactChat.mockReturnValueOnce(pending.promise);
    await user.click(compressButton());

    expect(screen.queryByText('compressNotNeeded')).toBeNull();
    expect(screen.getByRole('button', { name: 'compressing' })).toBeDisabled();
    expect(mockCompactChat).toHaveBeenCalledTimes(2);

    pending.resolve({ compacted: false, tokens_saved: 0 });
    expect(await screen.findByRole('button', { name: 'compressContext' })).toBeEnabled();
  });
});
