import { describe, expect, it } from 'vitest';

import {
  isExternalAgentDelegationReady,
  resolveExternalAgentBadgeKind,
  hasResolvableExternalCliBackend,
  hasAutoDetectedExternalCliBackend,
  hasExternalCliBackendAvailable,
} from '@/services/external-agents';

describe('external agent delegation badge helpers', () => {
  it('prefers readyForDelegation when present', () => {
    expect(
      isExternalAgentDelegationReady({
        authenticated: false,
        installed: false,
        readyForDelegation: true,
      }),
    ).toBe(true);
  });

  it('falls back to authenticated or installed', () => {
    expect(
      isExternalAgentDelegationReady({
        authenticated: false,
        installed: true,
        readyForDelegation: false,
      }),
    ).toBe(true);
    expect(
      isExternalAgentDelegationReady({
        authenticated: true,
        installed: false,
        readyForDelegation: false,
      }),
    ).toBe(true);
    expect(
      isExternalAgentDelegationReady({
        authenticated: false,
        installed: false,
        readyForDelegation: false,
      }),
    ).toBe(false);
  });

  it('resolves badge kind for third-party CLI setups', () => {
    expect(
      resolveExternalAgentBadgeKind({
        authenticated: false,
        installed: true,
        readyForDelegation: true,
      }),
    ).toBe('cli_ready');
    expect(
      resolveExternalAgentBadgeKind({
        authenticated: true,
        installed: true,
        readyForDelegation: true,
      }),
    ).toBe('subscription');
    expect(
      resolveExternalAgentBadgeKind({
        authenticated: false,
        installed: false,
        readyForDelegation: false,
      }),
    ).toBe('logged_out');
  });

  it('requires server confirmation for known backends but trusts unverifiable custom commands', () => {
    const claudeStatus = {
      backend: 'claude',
      installed: false,
      readyForDelegation: false,
    } as never;

    // An enabled known backend whose binary is missing from PATH must not read as ready.
    expect(hasResolvableExternalCliBackend([{ enabled: true, command: 'claude' }], [claudeStatus])).toBe(false);
    expect(
      hasResolvableExternalCliBackend(
        [{ enabled: true, command: 'claude' }],
        [{ backend: 'claude', installed: true, readyForDelegation: true } as never],
      ),
    ).toBe(true);

    // A command the server does not track cannot be verified, so explicit config wins.
    expect(hasResolvableExternalCliBackend([{ enabled: true, command: 'my-wrapper' }], [claudeStatus])).toBe(true);

    // A user-pinned absolute path is not a PATH lookup, so server detection cannot judge it.
    expect(
      hasResolvableExternalCliBackend([{ enabled: true, command: '/opt/homebrew/bin/claude' }], [claudeStatus]),
    ).toBe(true);

    // Disabled agents never count.
    expect(hasResolvableExternalCliBackend([{ enabled: false, command: 'claude' }], [claudeStatus])).toBe(false);
    expect(hasResolvableExternalCliBackend([], [])).toBe(false);

    expect(
      hasAutoDetectedExternalCliBackend([{ backend: 'claude', installed: true, readyForDelegation: true } as never]),
    ).toBe(true);
    expect(
      hasExternalCliBackendAvailable(
        [],
        [{ backend: 'claude', installed: true, readyForDelegation: true } as never],
        true,
      ),
    ).toBe(true);
    expect(
      hasExternalCliBackendAvailable(
        [],
        [{ backend: 'claude', installed: true, readyForDelegation: true } as never],
        false,
      ),
    ).toBe(false);
    expect(hasExternalCliBackendAvailable([{ enabled: true, command: 'claude' }], [claudeStatus], true)).toBe(false);
  });
});
