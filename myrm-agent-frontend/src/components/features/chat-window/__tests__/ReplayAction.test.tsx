import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ReplayDeterminismResponse } from '@/services/chat';
import { deferred } from '@/test-utils/deferred';

import ReplayAction from '../ReplayAction';

const kit = vi.hoisted(() => ({
  locale: 'en' as 'en' | 'zh',
  replayChatSession: vi.fn<(chatId: string) => Promise<unknown>>(),
  success: vi.fn<(text: string) => void>(),
  warning: vi.fn<(text: string) => void>(),
  error: vi.fn<(text: string) => void>(),
}));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => kit.locale));
vi.mock('@/services/chat', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/chat')>()),
  replayChatSession: kit.replayChatSession,
}));
vi.mock('@/hooks/shared/useToast', () => ({
  toast: { success: kit.success, warning: kit.warning, error: kit.error },
}));
vi.mock('../TrajectoryDiffModal', () => ({
  default: ({ open, currentSessionId, onClose }: { open: boolean; currentSessionId: string; onClose: () => void }) =>
    open ? (
      <dialog open aria-label="trajectory diff">
        {currentSessionId}
        <button type="button" onClick={onClose}>
          close diff
        </button>
      </dialog>
    ) : null,
}));

const replayResult = (score: number): ReplayDeterminismResponse => ({
  session_id: 'chat-1',
  determinism_score: score,
  tool_sequence_similarity: score,
  tool_set_jaccard: score,
  args_similarity: score,
  original_tool_count: 2,
  replayed_tool_count: 2,
  drifted_tools: [],
  verdict: 'DETERMINISTIC',
});

const replayButton = () => screen.getByRole('button', { name: /Verify(ing)? Replay/ });
const badge = () => screen.queryByTitle('Click to inspect trajectory differences');
const badgeIcon = () => badge()?.querySelector('svg')?.getAttribute('class') ?? '';

async function replayWith(score: number) {
  kit.replayChatSession.mockResolvedValue(replayResult(score));
  await act(async () => fireEvent.click(replayButton()));
}

beforeEach(() => {
  vi.resetAllMocks();
  kit.locale = 'en';
});

describe('ReplayAction', () => {
  it('offers the replay and shows no result before one has run', () => {
    render(<ReplayAction chatId="chat-1" />);

    expect(replayButton()).toBeEnabled();
    expect(replayButton()).toHaveAttribute('title', 'Replay session in an isolated environment and verify determinism');
    expect(badge()).toBeNull();
    expect(kit.replayChatSession).not.toHaveBeenCalled();
  });

  it('replays this chat once and keeps the button busy until the answer is there', async () => {
    const pending = deferred<ReplayDeterminismResponse>();
    kit.replayChatSession.mockReturnValue(pending.promise);
    render(<ReplayAction chatId="chat-1" />);

    fireEvent.click(replayButton());

    expect(kit.replayChatSession).toHaveBeenCalledExactlyOnceWith('chat-1');
    expect(replayButton()).toBeDisabled();
    expect(replayButton()).toHaveTextContent('Verifying Replay...');
    expect(replayButton().querySelector('svg')).toHaveClass('animate-spin');

    await act(async () => pending.resolve(replayResult(1)));

    expect(replayButton()).toBeEnabled();
    expect(replayButton()).toHaveTextContent('Verify Replay');
    expect(replayButton().querySelector('svg')).not.toHaveClass('animate-spin');
  });

  it('announces a deterministic replay and shows its score', async () => {
    render(<ReplayAction chatId="chat-1" />);

    await replayWith(1);

    expect(kit.success).toHaveBeenCalledExactlyOnceWith('Replay complete: High Deterministic Match (100%)');
    expect(kit.warning).not.toHaveBeenCalled();
    expect(badge()).toHaveTextContent('100% Match');
    expect(badge()?.className).toContain('emerald');
    expect(badgeIcon()).toContain('check');
  });

  it('counts 95% as deterministic and anything below as drift', async () => {
    render(<ReplayAction chatId="chat-1" />);

    await replayWith(0.95);
    expect(kit.success).toHaveBeenCalledExactlyOnceWith('Replay complete: High Deterministic Match (95%)');
    expect(badge()?.className).toContain('emerald');

    await replayWith(0.94);
    expect(kit.success).toHaveBeenCalledTimes(1);
    expect(kit.warning).toHaveBeenCalledExactlyOnceWith('Replay complete: Trajectory Drift Detected (94%)');
    expect(badge()).toHaveTextContent('94% Match');
    expect(badge()?.className).toContain('amber');
    expect(badgeIcon()).toContain('alert');
  });

  it('words the score in the current language', async () => {
    kit.locale = 'zh';
    kit.replayChatSession.mockResolvedValue(replayResult(1));
    render(<ReplayAction chatId="chat-1" />);

    await act(async () => fireEvent.click(screen.getByRole('button', { name: '重放验证' })));

    expect(screen.getByText('100% 吻合')).toBeInTheDocument();
  });

  it('rounds the score to a whole percent', async () => {
    render(<ReplayAction chatId="chat-1" />);

    await replayWith(0.876);

    expect(badge()).toHaveTextContent('88% Match');
  });

  it('reports a failed replay with the error text and leaves the button usable', async () => {
    kit.replayChatSession.mockRejectedValue(new Error('sandbox unavailable'));
    render(<ReplayAction chatId="chat-1" />);

    await act(async () => fireEvent.click(replayButton()));

    expect(kit.error).toHaveBeenCalledExactlyOnceWith('sandbox unavailable');
    expect(replayButton()).toBeEnabled();
    expect(badge()).toBeNull();
  });

  it('falls back to a generic message when the failure carries no error text', async () => {
    kit.replayChatSession.mockRejectedValue('nope');
    render(<ReplayAction chatId="chat-1" />);

    await act(async () => fireEvent.click(replayButton()));

    expect(kit.error).toHaveBeenCalledExactlyOnceWith('Replay verification failed');
  });

  it('replaces the score when the replay runs again', async () => {
    render(<ReplayAction chatId="chat-1" />);

    await replayWith(0.5);
    await replayWith(1);

    expect(badge()).toHaveTextContent('100% Match');
  });

  it('opens the trajectory comparison for this chat from the score and closes it again', async () => {
    render(<ReplayAction chatId="chat-1" />);
    await replayWith(1);
    expect(screen.queryByRole('dialog')).toBeNull();

    fireEvent.click(badge() as HTMLElement);
    expect(screen.getByRole('dialog', { name: 'trajectory diff' })).toHaveTextContent('chat-1');

    fireEvent.click(screen.getByRole('button', { name: 'close diff' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it.each(['{Enter}', ' '])('opens the comparison from the keyboard with %j', async (key) => {
    const user = userEvent.setup();
    render(<ReplayAction chatId="chat-1" />);
    await replayWith(1);

    badge()?.focus();
    await user.keyboard(key);

    expect(screen.getByRole('dialog', { name: 'trajectory diff' })).toBeInTheDocument();
  });

  it('offers the score as a button that can be reached by keyboard', async () => {
    render(<ReplayAction chatId="chat-1" />);
    await replayWith(1);

    expect(screen.getByRole('button', { name: /100% Match/ })).toBe(badge());
  });
});
