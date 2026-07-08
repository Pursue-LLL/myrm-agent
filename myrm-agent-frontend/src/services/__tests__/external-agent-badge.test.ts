import { describe, expect, it } from 'vitest';

import {
  isExternalAgentDelegationReady,
  resolveExternalAgentBadgeKind,
  hasExplicitExternalCliBackend,
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
      }),
    ).toBe(true);
    expect(
      isExternalAgentDelegationReady({
        authenticated: true,
        installed: false,
      }),
    ).toBe(true);
    expect(
      isExternalAgentDelegationReady({
        authenticated: false,
        installed: false,
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

  it('detects explicit config vs local auto-detect for backend availability', () => {
    expect(hasExplicitExternalCliBackend([{ enabled: true, command: 'claude' }])).toBe(true);
    expect(hasExplicitExternalCliBackend([])).toBe(false);
    expect(
      hasAutoDetectedExternalCliBackend([
        { backend: 'claude', installed: true, readyForDelegation: true } as never,
      ]),
    ).toBe(true);
    expect(
      hasExternalCliBackendAvailable([], [{ backend: 'claude', installed: true, readyForDelegation: true } as never], true),
    ).toBe(true);
    expect(
      hasExternalCliBackendAvailable([], [{ backend: 'claude', installed: true, readyForDelegation: true } as never], false),
    ).toBe(false);
  });
});
