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
const mockRunManualCompaction = vi.hoisted(() => vi.fn());

vi.mock('next-intl', () => ({
  useTranslations: () => translate,
}));

vi.mock('@/services/contextCompaction', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/contextCompaction')>()),
  runManualCompaction: mockRunManualCompaction,
}));

function renderControl({ chatId = 'chat-1' as string | null, usagePercent = 50 } = {}) {
  render(<ContextCompressControl chatId={chatId} usagePercent={usagePercent} />);
}

const compressButton = () => screen.getByRole('button', { name: /^compress/ });

describe('ContextCompressControl', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it.each([
    { usagePercent: 29.9, chatId: 'chat-1', enabled: false },
    { usagePercent: 30, chatId: 'chat-1', enabled: true },
    { usagePercent: 80, chatId: null, enabled: false },
  ])('usage $usagePercent with chat $chatId enables the button: $enabled', ({ usagePercent, chatId, enabled }) => {
    renderControl({ chatId, usagePercent });

    expect(compressButton().hasAttribute('disabled')).toBe(!enabled);
  });

  it('compresses without a topic and reports the saved tokens', async () => {
    mockRunManualCompaction.mockResolvedValue({
      compacted: true,
      tokens_saved: 15200,
      backup_path: '/tmp/backup.json',
    });
    renderControl();

    await userEvent.setup().click(compressButton());

    expect(await screen.findByText('compressSuccess:{"tokens":"15.2K"}')).toHaveClass('text-emerald-600');
    expect(mockRunManualCompaction).toHaveBeenCalledWith('chat-1', undefined);
  });

  it.each([
    { name: 'trims the typed focus topic', typed: '  auth module  ', sent: 'auth module' },
    { name: 'sends no focus topic for blank input', typed: '   ', sent: undefined },
  ])('$name', async ({ typed, sent }) => {
    mockRunManualCompaction.mockResolvedValue({ compacted: true, tokens_saved: 12000 });
    renderControl();
    const user = userEvent.setup();

    await user.type(screen.getByPlaceholderText('focusHintPlaceholder'), typed);
    await user.click(compressButton());

    await waitFor(() => {
      expect(mockRunManualCompaction).toHaveBeenCalledWith('chat-1', sent);
    });
  });

  it('stops typing and pasting the focus topic at the characters the server accepts', () => {
    renderControl();

    expect(screen.getByPlaceholderText('focusHintPlaceholder')).toHaveAttribute(
      'maxlength',
      String(COMPACT_FOCUS_TOPIC_MAX_LENGTH),
    );
  });

  it.each([
    { reason: 'no_compactable_messages', copy: 'chat.compact.skip.nothing', tone: 'text-muted-foreground' },
    { reason: 'concurrent_compaction_in_progress', copy: 'chat.compact.skip.busy', tone: 'text-muted-foreground' },
    { reason: 'summarize_circuit_open', copy: 'chat.compact.skip.paused', tone: 'text-amber-600' },
    { reason: 'timeout', copy: 'chat.compact.failed', tone: 'text-rose-600' },
  ])('words a compression the server did not run for its reason: $reason', async ({ reason, copy, tone }) => {
    mockRunManualCompaction.mockResolvedValue({ compacted: false, tokens_saved: 0, reason });
    renderControl();

    await userEvent.setup().click(compressButton());

    const outcome = await screen.findByText(copy);
    expect(outcome).toHaveClass(tone);
    expect(screen.queryByText(reason)).toBeNull();
  });

  it('shows a localized failure, not the raw message, when the request fails', async () => {
    mockRunManualCompaction.mockRejectedValue(new Error('Server error: 500'));
    renderControl();

    await userEvent.setup().click(compressButton());

    expect(await screen.findByText('chat.compact.failed')).toHaveClass('text-rose-600');
    expect(screen.queryByText(/Server error/)).toBeNull();
  });

  it('shows a busy button and drops the previous outcome while a new request runs', async () => {
    mockRunManualCompaction.mockResolvedValueOnce({
      compacted: false,
      tokens_saved: 0,
      reason: 'no_compactable_messages',
    });
    renderControl();
    const user = userEvent.setup();
    await user.click(compressButton());
    expect(await screen.findByText('chat.compact.skip.nothing')).toBeInTheDocument();

    const pending = deferred<{ compacted: boolean; tokens_saved: number; reason: string }>();
    mockRunManualCompaction.mockReturnValueOnce(pending.promise);
    await user.click(compressButton());

    expect(screen.queryByText('chat.compact.skip.nothing')).toBeNull();
    expect(screen.getByRole('button', { name: 'compressing' })).toBeDisabled();
    expect(mockRunManualCompaction).toHaveBeenCalledTimes(2);

    pending.resolve({ compacted: false, tokens_saved: 0, reason: 'no_compactable_messages' });
    expect(await screen.findByRole('button', { name: 'compressContext' })).toBeEnabled();
  });
});
