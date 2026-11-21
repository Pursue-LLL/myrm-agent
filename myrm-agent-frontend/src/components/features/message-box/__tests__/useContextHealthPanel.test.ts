/** @vitest-environment jsdom */
/**
 * What the context usage ring and its strategy panel show is the strategy health of the chat in view.
 *
 * Real scenario: the user opens the panel, switches chats, compresses the context, closes the panel. A read that
 * belongs to another chat, to a panel that has closed, or to the time before a compaction must never be shown.
 */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ContextHealth } from '@/services/contextHealth';
import type { SessionAnalytics } from '@/services/statistics';
import { deferred } from '@/test-utils/deferred';

import { useContextHealthPanel } from '../useContextHealthPanel';

const mockGetSessionAnalytics = vi.hoisted(() => vi.fn());

vi.mock('@/services/statistics', () => ({
  getSessionAnalytics: mockGetSessionAnalytics,
}));

const healthOf = (status: ContextHealth['status']) => ({ status }) as ContextHealth;
const analyticsOf = (status: ContextHealth['status']) => ({ context_health: healthOf(status) }) as SessionAnalytics;

type Props = { chatId: string | null; nonce: number };

function renderPanel(initial: Props = { chatId: 'chat-1', nonce: 0 }) {
  return renderHook(({ chatId, nonce }: Props) => useContextHealthPanel(chatId, nonce), { initialProps: initial });
}

describe('useContextHealthPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetSessionAnalytics.mockResolvedValue(analyticsOf('healthy'));
  });

  it('reads nothing while the panel is closed and the chat has not compacted', () => {
    const { result } = renderPanel();

    expect(mockGetSessionAnalytics).not.toHaveBeenCalled();
    expect(result.current).toMatchObject({ panelOpen: false, health: null, loading: false });
  });

  it('reads the chat when the panel opens and reports loading from that very render', async () => {
    const read = deferred<SessionAnalytics>();
    mockGetSessionAnalytics.mockReturnValue(read.promise);
    const { result } = renderPanel();

    act(() => result.current.setPanelOpen(true));

    expect(result.current).toMatchObject({ panelOpen: true, health: null, loading: true });
    expect(mockGetSessionAnalytics).toHaveBeenCalledWith('chat-1', false);

    await act(async () => read.resolve(analyticsOf('warning')));

    expect(result.current).toMatchObject({ health: healthOf('warning'), loading: false });
  });

  it('keeps the last health while the panel is closed and reads again, loading, on the next opening', async () => {
    const { result } = renderPanel();
    await act(async () => result.current.setPanelOpen(true));
    await act(async () => result.current.setPanelOpen(false));
    expect(result.current.health).toEqual(healthOf('healthy'));
    expect(mockGetSessionAnalytics).toHaveBeenCalledTimes(1);

    const second = deferred<SessionAnalytics>();
    mockGetSessionAnalytics.mockReturnValueOnce(second.promise);
    act(() => result.current.setPanelOpen(true));

    expect(result.current.loading).toBe(true);
    expect(mockGetSessionAnalytics).toHaveBeenCalledTimes(2);

    await act(async () => second.resolve(analyticsOf('critical')));
    expect(result.current).toMatchObject({ health: healthOf('critical'), loading: false });
  });

  it('leaves no health behind when the read fails', async () => {
    mockGetSessionAnalytics.mockRejectedValue(new Error('offline'));
    const { result } = renderPanel();

    await act(async () => result.current.setPanelOpen(true));

    expect(result.current).toMatchObject({ health: null, loading: false });
  });

  it('reads nothing without a chat, even with the panel open', async () => {
    const { result } = renderPanel({ chatId: null, nonce: 0 });

    await act(async () => result.current.setPanelOpen(true));

    expect(mockGetSessionAnalytics).not.toHaveBeenCalled();
    expect(result.current).toMatchObject({ health: null, loading: false });
  });

  describe('when the chat changes', () => {
    it('never shows the old chat health to the new chat, not even for one render', async () => {
      const seen: Array<{ chatId: string | null; health: ContextHealth | null }> = [];
      const { result, rerender } = renderHook(
        ({ chatId, nonce }: Props) => {
          const state = useContextHealthPanel(chatId, nonce);
          seen.push({ chatId, health: state.health });
          return state;
        },
        { initialProps: { chatId: 'chat-1', nonce: 0 } as Props },
      );
      await act(async () => result.current.setPanelOpen(true));
      expect(result.current.health).toEqual(healthOf('healthy'));
      mockGetSessionAnalytics.mockResolvedValue(analyticsOf('critical'));

      await act(async () => rerender({ chatId: 'chat-2', nonce: 0 }));

      const healthsSeenByChat2 = seen.filter((row) => row.chatId === 'chat-2').map((row) => row.health);
      expect(healthsSeenByChat2[0]).toBeNull();
      expect(healthsSeenByChat2).not.toContainEqual(healthOf('healthy'));
      expect(healthsSeenByChat2.at(-1)).toEqual(healthOf('critical'));
      expect(mockGetSessionAnalytics).toHaveBeenLastCalledWith('chat-2', false);
    });

    it('drops the health of the old chat even when the panel stays closed', async () => {
      const { result, rerender } = renderPanel();
      await act(async () => result.current.setPanelOpen(true));
      await act(async () => result.current.setPanelOpen(false));

      rerender({ chatId: 'chat-2', nonce: 0 });

      expect(result.current).toMatchObject({ health: null, loading: false });
      expect(mockGetSessionAnalytics).toHaveBeenCalledTimes(1);
    });

    it('ignores an answer for the old chat that arrives after the switch', async () => {
      const first = deferred<SessionAnalytics>();
      const second = deferred<SessionAnalytics>();
      mockGetSessionAnalytics.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
      const { result, rerender } = renderPanel();
      act(() => result.current.setPanelOpen(true));
      rerender({ chatId: 'chat-2', nonce: 0 });

      await act(async () => first.resolve(analyticsOf('critical')));
      expect(result.current).toMatchObject({ health: null, loading: true });

      await act(async () => second.resolve(analyticsOf('warning')));
      expect(result.current).toMatchObject({ health: healthOf('warning'), loading: false });
    });
  });

  describe('when the panel closes during a read', () => {
    it('drops that read and reads afresh on the next opening', async () => {
      const first = deferred<SessionAnalytics>();
      mockGetSessionAnalytics.mockReturnValueOnce(first.promise);
      const { result } = renderPanel();
      act(() => result.current.setPanelOpen(true));
      act(() => result.current.setPanelOpen(false));

      await act(async () => first.resolve(analyticsOf('critical')));
      expect(result.current).toMatchObject({ health: null, loading: false });

      await act(async () => result.current.setPanelOpen(true));
      expect(mockGetSessionAnalytics).toHaveBeenCalledTimes(2);
      expect(result.current.health).toEqual(healthOf('healthy'));
    });
  });

  describe('when the chat records a compaction', () => {
    it('reads past the analytics cache even while the panel is closed', async () => {
      const { rerender } = renderPanel();

      await act(async () => rerender({ chatId: 'chat-1', nonce: 1 }));

      expect(mockGetSessionAnalytics).toHaveBeenCalledTimes(1);
      expect(mockGetSessionAnalytics).toHaveBeenCalledWith('chat-1', true);
    });

    it('shows the health of the compaction, not the one cached before it', async () => {
      const { result, rerender } = renderPanel();
      await act(async () => result.current.setPanelOpen(true));
      mockGetSessionAnalytics.mockResolvedValue(analyticsOf('critical'));

      await act(async () => rerender({ chatId: 'chat-1', nonce: 1 }));

      expect(result.current.health).toEqual(healthOf('critical'));
    });

    it('keeps reading past the cache when the panel is opened afterwards', async () => {
      const { result, rerender } = renderPanel();
      await act(async () => rerender({ chatId: 'chat-1', nonce: 1 }));

      await act(async () => result.current.setPanelOpen(true));

      expect(mockGetSessionAnalytics).toHaveBeenCalledTimes(2);
      expect(mockGetSessionAnalytics).toHaveBeenLastCalledWith('chat-1', true);
    });

    it('goes quiet again once the chat switch resets the compaction counter', async () => {
      const { result, rerender } = renderPanel({ chatId: 'chat-1', nonce: 2 });
      await act(async () => Promise.resolve());
      expect(mockGetSessionAnalytics).toHaveBeenCalledTimes(1);

      await act(async () => rerender({ chatId: 'chat-2', nonce: 0 }));

      expect(mockGetSessionAnalytics).toHaveBeenCalledTimes(1);
      expect(result.current).toMatchObject({ health: null, loading: false });
    });
  });
});
