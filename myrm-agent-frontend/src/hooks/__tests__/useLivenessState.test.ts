import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

describe('useLivenessState', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch');
    vi.resetModules();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns idle by default then updates from API', async () => {
    fetchSpy.mockResolvedValue(new Response(JSON.stringify({ state: 'idle', agents: { activeCount: 0 } })));
    const { useLivenessState } = await import('../useLivenessState');
    const { result } = renderHook(() => useLivenessState());
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
    });
    expect(result.current.state).toBe('idle');
    expect(result.current.activeCount).toBe(0);
  });

  it('returns busy when API reports busy', async () => {
    fetchSpy.mockResolvedValue(new Response(JSON.stringify({ state: 'busy', agents: { activeCount: 2 } })));
    const { useLivenessState } = await import('../useLivenessState');
    const { result } = renderHook(() => useLivenessState());
    await waitFor(() => {
      expect(result.current.state).toBe('busy');
    });
    expect(result.current.activeCount).toBe(2);
    expect(result.current.tooltip).toContain('running');
  });

  it('returns degraded when API reports degraded', async () => {
    fetchSpy.mockResolvedValue(new Response(JSON.stringify({ state: 'degraded', agents: { activeCount: 0 } })));
    const { useLivenessState } = await import('../useLivenessState');
    const { result } = renderHook(() => useLivenessState());
    await waitFor(() => {
      expect(result.current.state).toBe('degraded');
    });
  });

  it('falls back to degraded on fetch error', async () => {
    fetchSpy.mockRejectedValue(new Error('Network error'));
    const { useLivenessState } = await import('../useLivenessState');
    const { result } = renderHook(() => useLivenessState());
    await waitFor(() => {
      expect(result.current.state).toBe('degraded');
    });
  });

  it('falls back to degraded on non-200 response', async () => {
    fetchSpy.mockResolvedValue(new Response('', { status: 503 }));
    const { useLivenessState } = await import('../useLivenessState');
    const { result } = renderHook(() => useLivenessState());
    await waitFor(() => {
      expect(result.current.state).toBe('degraded');
    });
  });

  it('falls back to degraded on invalid state string', async () => {
    fetchSpy.mockResolvedValue(new Response(JSON.stringify({ state: 'unknown_state', agents: { activeCount: 0 } })));
    const { useLivenessState } = await import('../useLivenessState');
    const { result } = renderHook(() => useLivenessState());
    await waitFor(() => {
      expect(result.current.state).toBe('degraded');
    });
  });

  it('handles plural tooltip for multiple tasks', async () => {
    fetchSpy.mockResolvedValue(new Response(JSON.stringify({ state: 'busy', agents: { activeCount: 3 } })));
    const { useLivenessState } = await import('../useLivenessState');
    const { result } = renderHook(() => useLivenessState());
    await waitFor(() => {
      expect(result.current.tooltip).toBe('3 tasks running');
    });
  });

  it('handles singular tooltip for single task', async () => {
    fetchSpy.mockResolvedValue(new Response(JSON.stringify({ state: 'busy', agents: { activeCount: 1 } })));
    const { useLivenessState } = await import('../useLivenessState');
    const { result } = renderHook(() => useLivenessState());
    await waitFor(() => {
      expect(result.current.tooltip).toBe('1 task running');
    });
  });

  it('stops poller when all consumers unmount', async () => {
    fetchSpy.mockResolvedValue(new Response(JSON.stringify({ state: 'idle', agents: { activeCount: 0 } })));
    const { useLivenessState } = await import('../useLivenessState');
    const { unmount } = renderHook(() => useLivenessState());
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
    });
    unmount();
    const countAfterUnmount = fetchSpy.mock.calls.length;
    await new Promise((r) => setTimeout(r, 100));
    expect(fetchSpy.mock.calls.length).toBe(countAfterUnmount);
  });
});
