import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import nacl from 'tweetnacl';
import type { E2EEClientSession } from '../client';

function makeSession(): E2EEClientSession {
  const kp = nacl.box.keyPair();
  return {
    sessionId: 'test-session-abc12345',
    clientSecretKey: kp.secretKey,
    serverPublicKey: kp.publicKey,
  };
}

const mockEnsureMobileE2EE = vi.fn<[], Promise<E2EEClientSession | null>>();
const mockLoadStoredE2EESession = vi.fn<[], E2EEClientSession | null>(() => null);

vi.mock('@/lib/mobileRemote', () => ({
  ensureMobileE2EE: (...args: []) => mockEnsureMobileE2EE(...args),
}));

vi.mock('@/lib/e2ee/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../client')>();
  return {
    ...actual,
    loadStoredE2EESession: (...args: []) => mockLoadStoredE2EESession(...args),
  };
});

describe('useE2EEStatus', () => {
  const originalSessionStorage = globalThis.sessionStorage;

  beforeEach(() => {
    mockEnsureMobileE2EE.mockReset();
    mockLoadStoredE2EESession.mockReset().mockReturnValue(null);

    const store = new Map<string, string>();
    Object.defineProperty(globalThis, 'sessionStorage', {
      configurable: true,
      value: {
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (key: string, value: string) => {
          store.set(key, value);
        },
        removeItem: (key: string) => {
          store.delete(key);
        },
        clear: () => {
          store.clear();
        },
      } as Storage,
    });
  });

  afterEach(() => {
    Object.defineProperty(globalThis, 'sessionStorage', {
      configurable: true,
      value: originalSessionStorage,
    });
  });

  it('starts with not established when no stored session', async () => {
    mockEnsureMobileE2EE.mockResolvedValue(null);

    const { useE2EEStatus } = await import('../useE2EEStatus');
    const { result } = renderHook(() => useE2EEStatus());

    expect(result.current.established).toBe(false);
    expect(result.current.fingerprint).toBeNull();
    expect(result.current.algorithm).toBe('NaCl Box (Curve25519)');
    expect(result.current.error).toBeNull();
  });

  it('sets established when ensureMobileE2EE succeeds', async () => {
    const session = makeSession();
    mockEnsureMobileE2EE.mockResolvedValue(session);
    mockLoadStoredE2EESession.mockReturnValue(session);

    const { useE2EEStatus } = await import('../useE2EEStatus');
    const { result } = renderHook(() => useE2EEStatus());

    await waitFor(() => {
      expect(result.current.established).toBe(true);
    });

    expect(typeof result.current.fingerprint).toBe('string');
    expect(result.current.fingerprint!).toMatch(/^[0-9a-f]{4}( [0-9a-f]{4}){3}$/);
    expect(result.current.sessionIdPrefix).toBe('test-ses');
  });

  it('sets error on E2EEHandshakeRequiredError', async () => {
    const { E2EEHandshakeRequiredError } = await import('../client');
    mockLoadStoredE2EESession.mockReturnValue(null);
    mockEnsureMobileE2EE.mockRejectedValue(
      new E2EEHandshakeRequiredError('handshake failed'),
    );

    const { useE2EEStatus } = await import('../useE2EEStatus');
    const { result } = renderHook(() => useE2EEStatus());

    await waitFor(() => {
      expect(result.current.error).toBe('handshake failed');
    });

    expect(result.current.established).toBe(false);
  });

  it('ignores non-E2EEHandshakeRequiredError errors', async () => {
    mockLoadStoredE2EESession.mockReturnValue(null);
    mockEnsureMobileE2EE.mockRejectedValue(new Error('network error'));

    const { useE2EEStatus } = await import('../useE2EEStatus');
    const { result } = renderHook(() => useE2EEStatus());

    await act(async () => {
      await vi.waitFor(() => {
        expect(mockEnsureMobileE2EE).toHaveBeenCalled();
      });
    });

    expect(result.current.error).toBeNull();
    expect(result.current.established).toBe(false);
  });

  it('does not update state after unmount (cancelled flag)', async () => {
    let resolveHandshake: (v: E2EEClientSession | null) => void;
    mockLoadStoredE2EESession.mockReturnValue(null);
    mockEnsureMobileE2EE.mockReturnValue(
      new Promise((resolve) => {
        resolveHandshake = resolve;
      }),
    );

    const { useE2EEStatus } = await import('../useE2EEStatus');
    const { result, unmount } = renderHook(() => useE2EEStatus());

    expect(result.current.established).toBe(false);

    unmount();
    resolveHandshake!(makeSession());

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });

    expect(result.current.established).toBe(false);
  });
});
