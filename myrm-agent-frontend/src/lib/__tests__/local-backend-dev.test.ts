import { describe, expect, it } from 'vitest';

import {
  formatLocalBackendSetupHint,
  isBootSessionCompleted,
} from '@/lib/local-backend-dev';

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
        frontend_proxy_port: 3000,
      }),
    ).toBe('hintSplitDev');
  });
});

describe('isBootSessionCompleted', () => {
  it('returns false when boot session key is absent', () => {
    sessionStorage.clear();
    expect(isBootSessionCompleted()).toBe(false);
  });

  it('returns true when boot session key is set', () => {
    sessionStorage.setItem('myrm_boot_shown', '1');
    expect(isBootSessionCompleted()).toBe(true);
  });
});
