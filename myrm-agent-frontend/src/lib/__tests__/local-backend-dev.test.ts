import { describe, expect, it, vi } from 'vitest';

import {
  formatLocalBackendSetupHint,
  isBootProfileCompleted,
  resolveBackendUnreachableMessage,
} from '@/lib/local-backend-dev';

vi.mock('@/lib/backend-health', () => ({
  fetchBackendHealth: vi.fn(() => Promise.resolve(null)),
}));

describe('formatLocalBackendSetupHint', () => {
  const t = (key: string) => key;

  it('returns hintUnreachable when health is null', () => {
    expect(formatLocalBackendSetupHint(t, null)).toBe('hintUnreachable');
  });

  it('returns hintSplitDev for healthy split_dev backend', () => {
    expect(
      formatLocalBackendSetupHint(t, {
        status: 'healthy',
        dev_mode: 'split_dev',
        listen_host: '127.0.0.1',
        listen_port: 8080,
        backend_port: 8080,
        webui_dev_port: 3000,
      }),
    ).toBe('hintSplitDev');
  });
});

describe('resolveBackendUnreachableMessage', () => {
  it('returns English unreachable hint when health is null', async () => {
    Object.defineProperty(globalThis.navigator, 'language', {
      configurable: true,
      value: 'en-US',
    });

    await expect(resolveBackendUnreachableMessage()).resolves.toContain('Backend not reachable');
  });
});

describe('isBootProfileCompleted', () => {
  it('returns false when boot profile key is absent', () => {
    localStorage.clear();
    expect(isBootProfileCompleted()).toBe(false);
  });

  it('returns true when boot profile key is set', () => {
    localStorage.setItem('myrm_boot_shown', '1');
    expect(isBootProfileCompleted()).toBe(true);
  });
});
