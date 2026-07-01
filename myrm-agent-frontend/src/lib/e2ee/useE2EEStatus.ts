import { useEffect, useMemo, useState } from 'react';
import { ensureMobileE2EE } from '@/lib/mobileRemote';
import { E2EEHandshakeRequiredError, loadStoredE2EESession } from '@/lib/e2ee/client';
import { computeE2EEFingerprint } from '@/lib/e2ee/fingerprint';

const E2EE_ALGORITHM = 'NaCl Box (Curve25519)';

export type E2EEStatus = {
  established: boolean;
  fingerprint: string | null;
  algorithm: string;
  sessionIdPrefix: string | null;
  error: string | null;
};

/**
 * Track mobile E2EE handshake state for UI indicators.
 * Returns fingerprint / algorithm / error so consumers only need this hook.
 */
export function useE2EEStatus(): E2EEStatus {
  const [established, setEstablished] = useState(() => loadStoredE2EESession() !== null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void ensureMobileE2EE()
      .then((session) => {
        if (!cancelled && session) setEstablished(true);
      })
      .catch((err: unknown) => {
        if (!cancelled && err instanceof E2EEHandshakeRequiredError) {
          setError(err.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const session = useMemo(() => (established ? loadStoredE2EESession() : null), [established]);

  return {
    established,
    fingerprint: session ? computeE2EEFingerprint(session.serverPublicKey) : null,
    algorithm: E2EE_ALGORITHM,
    sessionIdPrefix: session ? session.sessionId.slice(0, 8) : null,
    error,
  };
}
