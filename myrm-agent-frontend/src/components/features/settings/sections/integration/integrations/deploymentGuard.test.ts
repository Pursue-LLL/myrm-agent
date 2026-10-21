import { describe, expect, it } from 'vitest';

import { shouldBlockCloudLoopbackConnect, shouldBlockLocalOnlyInSandbox } from './deploymentGuard';

describe('shouldBlockLocalOnlyInSandbox', () => {
  it('blocks local-only entries in sandbox regardless of probe path', () => {
    expect(
      shouldBlockLocalOnlyInSandbox({
        isSandboxMode: true,
        isLocalTauriOnlyEntry: true,
      }),
    ).toBe(true);
  });

  it('does not block non-local-only entries in sandbox', () => {
    expect(
      shouldBlockLocalOnlyInSandbox({
        isSandboxMode: true,
        isLocalTauriOnlyEntry: false,
      }),
    ).toBe(false);
  });

  it('does not block local-only entries outside sandbox', () => {
    expect(
      shouldBlockLocalOnlyInSandbox({
        isSandboxMode: false,
        isLocalTauriOnlyEntry: true,
      }),
    ).toBe(false);
  });
});

describe('shouldBlockCloudLoopbackConnect', () => {
  it('blocks local-only loopback entries in sandbox when probe says cloud_not_supported', () => {
    expect(
      shouldBlockCloudLoopbackConnect({
        status: 'cloud_not_supported',
        isSandboxMode: true,
        isLocalTauriOnlyEntry: true,
      }),
    ).toBe(true);
  });

  it('does not block non-local-only entries in sandbox', () => {
    expect(
      shouldBlockCloudLoopbackConnect({
        status: 'cloud_not_supported',
        isSandboxMode: true,
        isLocalTauriOnlyEntry: false,
      }),
    ).toBe(false);
  });

  it('does not block local-only entries outside sandbox', () => {
    expect(
      shouldBlockCloudLoopbackConnect({
        status: 'cloud_not_supported',
        isSandboxMode: false,
        isLocalTauriOnlyEntry: true,
      }),
    ).toBe(false);
  });

  it('does not block on non-cloud probe statuses', () => {
    expect(
      shouldBlockCloudLoopbackConnect({
        status: 'reachable',
        isSandboxMode: true,
        isLocalTauriOnlyEntry: true,
      }),
    ).toBe(false);
  });
});
