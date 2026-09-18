import { describe, expect, it } from 'vitest';

import {
  isExternalAgentDelegationReady,
  resolveExternalAgentBadgeKind,
  resolveExternalCliReadiness,
  hasAutoDetectedExternalCliBackend,
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

  it('distinguishes not-configured from configured-but-unavailable', () => {
    const missing = { backend: 'claude', installed: false, readyForDelegation: false } as never;
    const present = { backend: 'claude', installed: true, readyForDelegation: true } as never;

    // Nothing configured: the user still has to add a backend.
    expect(resolveExternalCliReadiness([], [], true)).toBe('not_configured');
    expect(resolveExternalCliReadiness([{ enabled: false, command: 'claude' }], [], true)).toBe('not_configured');
    expect(resolveExternalCliReadiness([{ enabled: true, command: '   ' }], [], false)).toBe('not_configured');

    // Configured but the binary is missing: a different problem, needing a different fix.
    expect(resolveExternalCliReadiness([{ enabled: true, command: 'claude' }], [missing], true)).toBe('unavailable');

    // Ready once the server confirms the binary, or when the server cannot judge the command.
    expect(resolveExternalCliReadiness([{ enabled: true, command: 'claude' }], [present], true)).toBe('ready');
    expect(resolveExternalCliReadiness([{ enabled: true, command: 'my-wrapper' }], [missing], true)).toBe('ready');
    expect(
      resolveExternalCliReadiness([{ enabled: true, command: '/opt/homebrew/bin/claude' }], [missing], true),
    ).toBe('ready');

    // A derived or wrapped binary is a different program the server cannot vouch for, so
    // it must not inherit another backend's negative detection result.
    expect(resolveExternalCliReadiness([{ enabled: true, command: 'claude-bedrock' }], [missing], true)).toBe('ready');
    expect(resolveExternalCliReadiness([{ enabled: true, command: 'my-claude-wrapper' }], [missing], true)).toBe(
      'ready',
    );

    // A locally auto-detected CLI counts as ready even with nothing configured in-app.
    expect(resolveExternalCliReadiness([], [present], true)).toBe('ready');
    expect(resolveExternalCliReadiness([], [present], false)).toBe('not_configured');
    // A whitespace-only command cannot match any backend row and must not read as ready.
    expect(resolveExternalCliReadiness([{ enabled: true, command: '   ' }], [present], true)).toBe('not_configured');
    expect(
      hasAutoDetectedExternalCliBackend([{ backend: 'claude', installed: true, readyForDelegation: true } as never]),
    ).toBe(true);
  });
});
