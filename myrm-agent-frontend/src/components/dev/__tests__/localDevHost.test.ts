import { afterEach, describe, expect, it, vi } from 'vitest';

import { isLocalDevHost } from '@/components/dev/localDevHost';

const originalLocation = window.location;

function setHostname(hostname: string): void {
  Object.defineProperty(window, 'location', { configurable: true, value: { hostname } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
});

describe('isLocalDevHost', () => {
  it.each(['127.0.0.1', 'localhost'])('accepts the loopback host %s', (host) => {
    setHostname(host);
    expect(isLocalDevHost()).toBe(true);
  });

  it.each(['127.0.0.1', 'localhost'])('rejects the loopback host %s in a production build', (host) => {
    vi.stubEnv('NODE_ENV', 'production');
    setHostname(host);
    expect(isLocalDevHost()).toBe(false);
  });

  it.each(['', '[::1]', '0.0.0.0', '192.168.1.5', 'example.com', 'localhost.evil.com', '127.0.0.1.evil.com'])(
    'rejects %j so a dev bridge never mounts there',
    (host) => {
      setHostname(host);
      expect(isLocalDevHost()).toBe(false);
    },
  );

  it('is false without a window (server render)', () => {
    vi.stubGlobal('window', undefined);
    expect(isLocalDevHost()).toBe(false);
  });
});
