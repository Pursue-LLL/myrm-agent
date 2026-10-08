import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { usePendingMemoryToast } from '@/hooks/shared/usePendingMemoryToast';
import { useMemoryStore } from '@/store/memory';

const mocks = vi.hoisted(() => ({
  getPendingMemories: vi.fn(),
  toast: vi.fn(),
}));

const stableT = (key: string, values?: Record<string, number>) => (values ? `${key}:${values.count}` : key);
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/shared/useToast', () => ({ toast: mocks.toast }));

vi.mock('@/lib/deploy-mode', () => ({ isLocalMode: () => true }));

vi.mock('@/services/memory', () => ({
  getPendingMemories: (...args: unknown[]) => mocks.getPendingMemories(...args),
}));

const queue = (total: number) => ({ items: [], total });

describe('usePendingMemoryToast', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMemoryStore.setState({ pendingMemories: [], pendingCount: 0, pendingLoading: false, pendingError: null });
  });

  it('does not toast for a backlog that already exists on first load', async () => {
    mocks.getPendingMemories.mockResolvedValue(queue(3));

    renderHook(() => usePendingMemoryToast());

    await waitFor(() => expect(useMemoryStore.getState().pendingCount).toBe(3));
    expect(mocks.toast).not.toHaveBeenCalled();
  });

  it('toasts the number of proposals added after the baseline', async () => {
    mocks.getPendingMemories.mockResolvedValueOnce(queue(3));
    renderHook(() => usePendingMemoryToast());
    await waitFor(() => expect(useMemoryStore.getState().pendingCount).toBe(3));

    mocks.getPendingMemories.mockResolvedValueOnce(queue(5));
    await act(async () => {
      await useMemoryStore.getState().fetchPendingMemories(true);
    });

    expect(mocks.toast).toHaveBeenCalledOnce();
    expect(mocks.toast).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'pendingToast.title', description: 'pendingToast.description:2' }),
    );
  });

  it('stays quiet when the queue shrinks and re-baselines for the next increase', async () => {
    mocks.getPendingMemories.mockResolvedValueOnce(queue(3));
    renderHook(() => usePendingMemoryToast());
    await waitFor(() => expect(useMemoryStore.getState().pendingCount).toBe(3));

    mocks.getPendingMemories.mockResolvedValueOnce(queue(1));
    await act(async () => {
      await useMemoryStore.getState().fetchPendingMemories(true);
    });
    expect(mocks.toast).not.toHaveBeenCalled();

    mocks.getPendingMemories.mockResolvedValueOnce(queue(2));
    await act(async () => {
      await useMemoryStore.getState().fetchPendingMemories(true);
    });
    expect(mocks.toast).toHaveBeenCalledWith(expect.objectContaining({ description: 'pendingToast.description:1' }));
  });

  it('treats the first successful refresh after a failed first load as the baseline', async () => {
    mocks.getPendingMemories.mockRejectedValueOnce(new Error('offline'));
    renderHook(() => usePendingMemoryToast());
    await waitFor(() => expect(useMemoryStore.getState().pendingError).toBe('offline'));

    mocks.getPendingMemories.mockResolvedValueOnce(queue(5));
    await act(async () => {
      await useMemoryStore.getState().fetchPendingMemories(true);
    });
    expect(mocks.toast).not.toHaveBeenCalled();

    mocks.getPendingMemories.mockResolvedValueOnce(queue(7));
    await act(async () => {
      await useMemoryStore.getState().fetchPendingMemories(true);
    });
    expect(mocks.toast).toHaveBeenCalledOnce();
    expect(mocks.toast).toHaveBeenCalledWith(expect.objectContaining({ description: 'pendingToast.description:2' }));
  });

  it('stops observing the store after unmount', async () => {
    mocks.getPendingMemories.mockResolvedValueOnce(queue(0));
    const { unmount } = renderHook(() => usePendingMemoryToast());
    await waitFor(() => expect(mocks.getPendingMemories).toHaveBeenCalledOnce());
    unmount();

    mocks.getPendingMemories.mockResolvedValueOnce(queue(4));
    await act(async () => {
      await useMemoryStore.getState().fetchPendingMemories(true);
    });

    expect(mocks.toast).not.toHaveBeenCalled();
  });
});
