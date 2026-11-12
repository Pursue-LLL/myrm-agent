import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/deploy-mode', () => ({
  getBackendBaseUrl: () => '',
  isLocalMode: () => true,
}));

vi.mock('@/lib/backend-health-probe', () => ({
  BACKEND_HEALTH_MAX_ATTEMPTS: 2,
  BACKEND_HEALTH_POLL_INTERVAL_MS: 1,
  waitForBackendReady: vi.fn(async () => true),
  waitForTauriRuntime: vi.fn(async () => true),
}));

vi.mock('@/lib/tauri', () => ({
  isTauriEnvironment: vi.fn(() => false),
  listenTauriEvent: vi.fn(async () => () => undefined),
}));

interface PollOptions {
  signal?: AbortSignal;
  maxAttempts?: number;
}

/** A backend that never answers: the poll only ends when its signal aborts. */
function parkUntilAborted({ signal }: PollOptions = {}): Promise<boolean> {
  return new Promise((resolve) => {
    signal?.addEventListener('abort', () => resolve(false), { once: true });
  });
}

// `vi.resetModules()` keeps the mocked modules (and their `vi.fn`s), so each test starts from explicit defaults.
beforeEach(async () => {
  vi.resetModules();
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, json: async () => ({ ready: true, checks: { database: true } }) }) as Response),
  );
  const probe = await import('@/lib/backend-health-probe');
  const tauri = await import('@/lib/tauri');
  vi.mocked(probe.waitForBackendReady).mockReset().mockResolvedValue(true);
  vi.mocked(probe.waitForTauriRuntime).mockReset().mockResolvedValue(true);
  vi.mocked(tauri.isTauriEnvironment).mockReset().mockReturnValue(false);
  vi.mocked(tauri.listenTauriEvent)
    .mockReset()
    .mockResolvedValue(() => undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('platform-readiness', () => {
  it('resolves when database check passes', async () => {
    const { whenDatabaseReady, resetPlatformReadinessForTests } = await import('@/lib/platform-readiness');
    resetPlatformReadinessForTests();
    await expect(whenDatabaseReady()).resolves.toBe(true);
  });

  it('marks unreachable and re-warms after transport failure', async () => {
    const { getPlatformReadinessSnapshot, markPlatformUnreachable, resetPlatformReadinessForTests } =
      await import('@/lib/platform-readiness');
    resetPlatformReadinessForTests();
    markPlatformUnreachable();
    expect(getPlatformReadinessSnapshot().state).toBe('unreachable');
  });

  it('keeps one warm in flight when an invalidated warm finishes after its replacement started', async () => {
    const probe = await import('@/lib/backend-health-probe');
    const readiness = await import('@/lib/platform-readiness');
    readiness.resetPlatformReadinessForTests();
    const settle: Array<(healthy: boolean) => void> = [];
    vi.mocked(probe.waitForBackendReady).mockImplementation(
      () => new Promise<boolean>((resolve) => settle.push(resolve)),
    );

    const first = readiness.ensurePlatformReadiness();
    await vi.waitFor(() => expect(settle).toHaveLength(1));
    readiness.markPlatformUnreachable();
    const second = readiness.ensurePlatformReadiness();
    await vi.waitFor(() => expect(settle).toHaveLength(2));

    settle[0](false);
    await first;

    expect(readiness.ensurePlatformReadiness()).toBe(second);
    settle[1](false);
    await second;
  });
});

describe('platform-readiness shell failure events', () => {
  /** Loads the module inside the desktop shell; `emit` plays the shell delivering an event. */
  async function loadInsideShell() {
    const probe = await import('@/lib/backend-health-probe');
    const tauri = await import('@/lib/tauri');
    const readiness = await import('@/lib/platform-readiness');
    const handlers = new Map<string, () => void>();
    vi.mocked(tauri.isTauriEnvironment).mockReturnValue(true);
    vi.mocked(tauri.listenTauriEvent).mockImplementation(async (event, handler) => {
      handlers.set(event, () => handler({}));
      return () => undefined;
    });
    readiness.resetPlatformReadinessForTests();
    const emit = (event: string): void => handlers.get(event)?.();
    return { probe, tauri, readiness, handlers, emit };
  }

  it.each(['backend-start-failed', 'backend-crash-loop'])(
    'ends a parked wait at once when the shell reports %s',
    async (event) => {
      const { probe, readiness, handlers, emit } = await loadInsideShell();
      vi.mocked(probe.waitForBackendReady).mockImplementation(parkUntilAborted);

      const parked = readiness.whenDatabaseReady();
      await vi.waitFor(() => expect(handlers.has(event)).toBe(true));
      emit(event);

      await expect(parked).resolves.toBe(false);
      expect(readiness.getPlatformReadinessSnapshot().state).toBe('unreachable');
    },
  );

  it('ends every parked wait, including one an invalidation detached from the single-flight', async () => {
    const { probe, readiness, handlers, emit } = await loadInsideShell();
    vi.mocked(probe.waitForBackendReady).mockImplementation(parkUntilAborted);

    const detached = readiness.whenDatabaseReady();
    await vi.waitFor(() => expect(handlers.size).toBeGreaterThan(0));
    readiness.markPlatformUnreachable();
    const replacement = readiness.whenDatabaseReady();
    await vi.waitFor(() => expect(probe.waitForBackendReady).toHaveBeenCalledTimes(2));
    emit('backend-crash-loop');

    await expect(Promise.all([detached, replacement])).resolves.toEqual([false, false]);
  });

  it('keeps waiting through a crash the watchdog restarts', async () => {
    const { probe, readiness, handlers } = await loadInsideShell();
    vi.mocked(probe.waitForBackendReady).mockImplementation(parkUntilAborted);

    const parked = readiness.whenDatabaseReady();
    await vi.waitFor(() => expect(handlers.size).toBeGreaterThan(0));

    expect([...handlers.keys()].sort()).toEqual(['backend-crash-loop', 'backend-start-failed']);
    readiness.resetPlatformReadinessForTests();
    await expect(parked).resolves.toBe(false);
  });

  it('fails a later wait after one probe until the backend answers, then restores the full budget', async () => {
    const { probe, readiness, handlers, emit } = await loadInsideShell();
    vi.mocked(probe.waitForBackendReady).mockImplementation(parkUntilAborted);

    const parked = readiness.whenDatabaseReady();
    await vi.waitFor(() => expect(handlers.has('backend-crash-loop')).toBe(true));
    expect(vi.mocked(probe.waitForBackendReady).mock.calls[0][0]).not.toHaveProperty('maxAttempts');
    emit('backend-crash-loop');
    await parked;

    vi.mocked(probe.waitForBackendReady).mockReset().mockResolvedValue(false);
    await expect(readiness.whenDatabaseReady()).resolves.toBe(false);
    expect(probe.waitForBackendReady).toHaveBeenCalledTimes(1);
    expect(probe.waitForBackendReady).toHaveBeenLastCalledWith(expect.objectContaining({ maxAttempts: 1 }));

    vi.mocked(probe.waitForBackendReady).mockReset().mockResolvedValue(true);
    await expect(readiness.whenDatabaseReady()).resolves.toBe(true);

    readiness.markPlatformUnreachable();
    vi.mocked(probe.waitForBackendReady).mockClear();
    await expect(readiness.whenDatabaseReady()).resolves.toBe(true);
    expect(vi.mocked(probe.waitForBackendReady).mock.calls[0][0]).not.toHaveProperty('maxAttempts');
  });

  it('does not subscribe outside the desktop shell', async () => {
    const { tauri, readiness } = await loadInsideShell();
    vi.mocked(tauri.isTauriEnvironment).mockReturnValue(false);

    await expect(readiness.whenDatabaseReady()).resolves.toBe(true);

    expect(tauri.listenTauriEvent).not.toHaveBeenCalled();
  });

  it('subscribes once per page and retries a subscription the bridge rejected', async () => {
    const { tauri, readiness } = await loadInsideShell();
    vi.mocked(tauri.listenTauriEvent).mockRejectedValueOnce(new Error('bridge unavailable'));

    await readiness.whenDatabaseReady();
    await vi.waitFor(() => expect(tauri.listenTauriEvent).toHaveBeenCalledTimes(2));

    readiness.markPlatformUnreachable();
    await readiness.whenDatabaseReady();
    expect(tauri.listenTauriEvent).toHaveBeenCalledTimes(4);

    readiness.markPlatformUnreachable();
    await readiness.whenDatabaseReady();
    expect(tauri.listenTauriEvent).toHaveBeenCalledTimes(4);
  });
});
