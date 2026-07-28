import { renderHook, act } from '@testing-library/react';
import { useCrashLoopGuard } from '../useCrashLoopGuard';

let mockIsTauri = false;
let eventHandlers: Record<string, ((event: unknown) => void)[]> = {};
const mockUnlisten = vi.fn();

vi.mock('@/lib/tauri', () => ({
  isTauriEnvironment: () => mockIsTauri,
  listenTauriEvent: vi.fn(async (event: string, handler: (e: unknown) => void) => {
    if (!eventHandlers[event]) eventHandlers[event] = [];
    eventHandlers[event].push(handler);
    return mockUnlisten;
  }),
}));

function emitEvent(event: string, payload?: unknown) {
  const handlers = eventHandlers[event] || [];
  for (const h of handlers) {
    h({ event, payload, id: 1 });
  }
}

describe('useCrashLoopGuard', () => {
  beforeEach(() => {
    mockIsTauri = false;
    eventHandlers = {};
    mockUnlisten.mockClear();
  });

  it('should not activate in non-Tauri environment', () => {
    mockIsTauri = false;
    const { result } = renderHook(() => useCrashLoopGuard());

    expect(result.current.crashLoopActive).toBe(false);
    expect(result.current.errorMessage).toBeNull();
  });

  it('should activate on backend-crash-loop event with string payload', async () => {
    mockIsTauri = true;
    const { result } = renderHook(() => useCrashLoopGuard());

    await vi.waitFor(() => {
      expect(eventHandlers['backend-crash-loop']).toBeDefined();
    });

    act(() => {
      emitEvent('backend-crash-loop', 'Port 8080 already in use');
    });

    expect(result.current.crashLoopActive).toBe(true);
    expect(result.current.errorMessage).toBe('Port 8080 already in use');
  });

  it('should activate with null errorMessage when payload is empty string', async () => {
    mockIsTauri = true;
    const { result } = renderHook(() => useCrashLoopGuard());

    await vi.waitFor(() => {
      expect(eventHandlers['backend-crash-loop']).toBeDefined();
    });

    act(() => {
      emitEvent('backend-crash-loop', '');
    });

    expect(result.current.crashLoopActive).toBe(true);
    expect(result.current.errorMessage).toBeNull();
  });

  it('should activate with null errorMessage when payload is non-string', async () => {
    mockIsTauri = true;
    const { result } = renderHook(() => useCrashLoopGuard());

    await vi.waitFor(() => {
      expect(eventHandlers['backend-crash-loop']).toBeDefined();
    });

    act(() => {
      emitEvent('backend-crash-loop', undefined);
    });

    expect(result.current.crashLoopActive).toBe(true);
    expect(result.current.errorMessage).toBeNull();
  });

  it('should reset state on dismiss', async () => {
    mockIsTauri = true;
    const { result } = renderHook(() => useCrashLoopGuard());

    await vi.waitFor(() => {
      expect(eventHandlers['backend-crash-loop']).toBeDefined();
    });

    act(() => {
      emitEvent('backend-crash-loop', 'Fatal error');
    });

    expect(result.current.crashLoopActive).toBe(true);
    expect(result.current.errorMessage).toBe('Fatal error');

    act(() => {
      result.current.dismiss();
    });

    expect(result.current.crashLoopActive).toBe(false);
    expect(result.current.errorMessage).toBeNull();
  });

  it('should call unlisten on unmount', async () => {
    mockIsTauri = true;
    const { unmount } = renderHook(() => useCrashLoopGuard());

    await vi.waitFor(() => {
      expect(eventHandlers['backend-crash-loop']).toBeDefined();
    });

    unmount();
    expect(mockUnlisten).toHaveBeenCalled();
  });
});
