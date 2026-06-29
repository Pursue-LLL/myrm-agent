import { afterEach, describe, expect, it, vi } from 'vitest';

import { waitForBackendReady, waitForTauriRuntime } from '@/lib/backend-health';
import { tauriBackend } from '@/lib/tauri';

vi.mock('@/lib/deploy-mode', () => ({
  getDeployMode: vi.fn(() => 'tauri'),
  isLocalMode: vi.fn(() => true),
}));

vi.mock('@/lib/local-backend-dev', () => ({
  isBootSessionCompleted: vi.fn(() => false),
}));

vi.mock('@/lib/tauri', () => ({
  isTauriEnvironment: vi.fn(() => true),
  tauriBackend: {
    checkHealth: vi.fn(),
  },
}));

const { getDeployMode } = await import('@/lib/deploy-mode');
const { isTauriEnvironment } = await import('@/lib/tauri');

describe('waitForTauriRuntime', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('returns true immediately when deploy mode is not tauri', async () => {
    vi.mocked(getDeployMode).mockReturnValue('local');
    vi.mocked(isTauriEnvironment).mockReturnValue(false);

    await expect(waitForTauriRuntime()).resolves.toBe(true);
    expect(isTauriEnvironment).not.toHaveBeenCalled();
  });

  it('polls until tauri runtime is injected', async () => {
    vi.mocked(getDeployMode).mockReturnValue('tauri');
    vi.mocked(isTauriEnvironment)
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);

    await expect(waitForTauriRuntime({ pollIntervalMs: 1, maxAttempts: 5 })).resolves.toBe(true);
    expect(isTauriEnvironment).toHaveBeenCalledTimes(3);
  });
});

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

describe('checkBackendReadyOnce', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('delegates to tauri health probe when in tauri runtime', async () => {
    vi.mocked(isTauriEnvironment).mockReturnValue(true);
    vi.mocked(tauriBackend.checkHealth).mockResolvedValue(true);

    const { checkBackendReadyOnce } = await import('@/lib/backend-health');
    await expect(checkBackendReadyOnce()).resolves.toBe(true);
    expect(tauriBackend.checkHealth).toHaveBeenCalledTimes(1);
  });
});

describe('ensureLocalBackendReady', () => {
  afterEach(() => {
    vi.clearAllMocks();
    void import('@/lib/backend-health').then(({ resetLocalBackendReadyGate }) => {
      resetLocalBackendReadyGate();
    });
  });

  it('uses single probe when boot session is completed', async () => {
    const { isBootSessionCompleted } = await import('@/lib/local-backend-dev');
    vi.mocked(isBootSessionCompleted).mockReturnValue(true);
    vi.mocked(isTauriEnvironment).mockReturnValue(true);
    vi.mocked(tauriBackend.checkHealth).mockResolvedValue(false);

    const { ensureLocalBackendReady, resetLocalBackendReadyGate } = await import('@/lib/backend-health');
    resetLocalBackendReadyGate();

    await expect(ensureLocalBackendReady()).resolves.toBe(false);
    expect(tauriBackend.checkHealth).toHaveBeenCalledTimes(1);
  });
});
