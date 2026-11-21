/** @vitest-environment jsdom */
/**
 * After the context is compressed, the open strategy panel shows the health that compression produced.
 *
 * Real scenario: the user opens the panel and compresses the context; the chat then records the compaction. The
 * analytics service keeps a chat's answer for 30 s, so a read that goes through that cache still shows the numbers
 * from before the compression. Runs the real chat store, the real analytics service (only its HTTP call is replaced)
 * and the real English copy.
 *
 * The compress control belongs to the open panel too: what the user typed in it and the outcome line of the compression
 * stay put while that read runs.
 */
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ContextHealth } from '@/services/contextHealth';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';

import ContextUsageIndicator from '../ContextUsageIndicator';

const mockApiRequest = vi.hoisted(() => vi.fn());

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiRequest: mockApiRequest,
}));

vi.mock('@/services/chat', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/chat')>()),
  getChatDetail: vi.fn().mockResolvedValue({ chat: { compacted_summary: null, compacted_before_id: null } }),
  listContextBranches: vi.fn().mockResolvedValue([]),
  getContextPins: vi.fn().mockResolvedValue({ files: [] }),
}));

vi.mock('@/hooks/ui/useMediaQuery', () => ({
  useIsMobile: () => false,
}));

const healthAfter = (compactions: number, tokensSaved: number) =>
  ({
    status: 'healthy',
    compaction: { active: true, count: compactions, tokens_saved: tokensSaved },
    pruning: { active: false, archived: 0, archive_restore_blocked_count: 0 },
    cache: { active: false, cache_hit_rate: 0 },
  }) as ContextHealth;

// The analytics cache outlives a test, so every test gets a chat of its own.
let chatSeq = 0;

const analyticsReads = (chatId: string) =>
  mockApiRequest.mock.calls.filter(([url]) => url === `/statistics/session/${chatId}`);

describe('ContextUsageIndicator after a compaction', () => {
  let chatId: string;

  beforeEach(() => {
    vi.clearAllMocks();
    chatId = `chat-compaction-${++chatSeq}`;
    useConfigStore.setState({ showContextUsage: true });
    useChatStore.setState({
      chatId,
      compactionRefreshNonce: 0,
      messages: [
        {
          messageId: 'm1',
          chatId,
          createdAt: new Date(),
          role: 'assistant',
          content: 'Hello',
          contextBudget: {
            current_tokens: 60000,
            max_context_tokens: 128000,
            usage_percent: 47,
            health_status: 'healthy',
          },
        },
      ],
    });
  });

  it('shows the health the compaction produced, not the numbers cached before it, and reads once for it', async () => {
    mockApiRequest
      .mockResolvedValueOnce({ context_health: healthAfter(3, 8200) })
      .mockResolvedValueOnce({ context_health: healthAfter(4, 14200) });
    render(<ContextUsageIndicator />);
    await userEvent.setup().click(screen.getByTestId('context-usage-indicator'));
    expect(await screen.findByText('3× compressed, 8.2K saved')).toBeInTheDocument();

    await act(async () => {
      await useChatStore.getState().refreshCompactionState(chatId, { tokensSaved: 6000 });
    });

    expect(await screen.findByText('4× compressed, 14.2K saved')).toBeInTheDocument();
    expect(analyticsReads(chatId)).toHaveLength(2);
  });

  it('keeps the typed focus topic and the outcome line through the health read a compression triggers', async () => {
    const healths = [healthAfter(3, 8200), healthAfter(4, 14200)];
    mockApiRequest.mockImplementation(async (url: string) =>
      url === `/chats/${chatId}/compact`
        ? { compacted: true, message_count: 6, tokens_saved: 6000, reason: null }
        : { context_health: healths.shift() },
    );
    const user = userEvent.setup();
    render(<ContextUsageIndicator />);
    await user.click(screen.getByTestId('context-usage-indicator'));
    expect(await screen.findByText('3× compressed, 8.2K saved')).toBeInTheDocument();

    const topicInput = screen.getByPlaceholderText('Focus topic (optional, e.g. auth module)');
    await user.type(topicInput, 'billing');
    await user.click(screen.getByRole('button', { name: 'Compress context' }));

    expect(await screen.findByText('4× compressed, 14.2K saved')).toBeInTheDocument();
    expect(screen.getByText('Saved 6.0K tokens')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Focus topic (optional, e.g. auth module)')).toBe(topicInput);
    expect(topicInput).toHaveValue('billing');
  });
});
