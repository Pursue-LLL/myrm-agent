import { afterEach, describe, expect, it, vi } from 'vitest';

import { waitForBackendReady } from '@/lib/backend-health';
import { tauriBackend } from '@/lib/tauri';

vi.mock('@/lib/tauri', () => ({
  isTauriEnvironment: vi.fn(() => true),
  tauriBackend: {
    checkHealth: vi.fn(),
  },
}));

const { isTauriEnvironment } = await import('@/lib/tauri');

describe('waitForBackendReady', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('returns true immediately when tauri health succeeds on first probe', async () => {
    vi.mocked(isTauriEnvironment).mockReturnValue(true);
    vi.mocked(tauriBackend.checkHealth).mockResolvedValue(true);

    await expect(waitForBackendReady()).resolves.toBe(true);
    expect(tauriBackend.checkHealth).toHaveBeenCalledTimes(1);
  });

  it('polls until tauri health succeeds', async () => {
    vi.mocked(isTauriEnvironment).mockReturnValue(true);
    vi.mocked(tauriBackend.checkHealth)
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true);

    await expect(
      waitForBackendReady({ pollIntervalMs: 1, maxAttempts: 5 }),
    ).resolves.toBe(true);
    expect(tauriBackend.checkHealth).toHaveBeenCalledTimes(3);
  });

  it('returns false after max attempts', async () => {
    vi.mocked(isTauriEnvironment).mockReturnValue(true);
    vi.mocked(tauriBackend.checkHealth).mockResolvedValue(false);

    await expect(
      waitForBackendReady({ pollIntervalMs: 1, maxAttempts: 3 }),
    ).resolves.toBe(false);
    expect(tauriBackend.checkHealth).toHaveBeenCalledTimes(3);
  });

  it('returns false when aborted before success', async () => {
    vi.mocked(isTauriEnvironment).mockReturnValue(true);
    vi.mocked(tauriBackend.checkHealth).mockResolvedValue(false);
    const controller = new AbortController();

    const pending = waitForBackendReady({
      pollIntervalMs: 50,
      maxAttempts: 10,
      signal: controller.signal,
    });

    controller.abort();
    await expect(pending).resolves.toBe(false);
  });
});
