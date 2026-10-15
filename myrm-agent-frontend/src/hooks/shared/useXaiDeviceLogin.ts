'use client';

/**
 * [INPUT]
 * @/services/xai-oauth::startXaiOAuth, pollXaiOAuth (POS: device-code login endpoints of the server)
 * @/store/config/providerSubscription::connectProviderSubscription (POS: store-side effects of a successful login)
 *
 * [OUTPUT]
 * useXaiDeviceLogin: starts, polls and cancels a device-code login and exposes its phase, user code and verification URL
 * XaiLoginFailure: closed set of reasons a login ends without a connection
 * XaiDeviceLogin: the shape the hook returns
 *
 * [POS]
 * The one device-code login flow (RFC 8628) for the xAI subscription, shared by the chat banner, the Models page and
 * the Credentials page. It owns the polling schedule and the connected state; the surfaces own presentation only.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  pollXaiOAuth,
  startXaiOAuth,
  type XaiOAuthPollResponse,
  type XaiOAuthStartResponse,
} from '@/services/xai-oauth';
import { connectProviderSubscription } from '@/store/config/providerSubscription';

const XAI_PROVIDER_ID = 'xai';

const DEFAULT_POLL_INTERVAL_S = 5;
const MIN_POLL_INTERVAL_MS = 1000;
/** RFC 8628 section 3.5: a `slow_down` answer raises the interval by five seconds for every later poll. */
const SLOW_DOWN_STEP_MS = 5000;
/** Device codes are valid for ten minutes unless the server says otherwise. */
const DEFAULT_LIFETIME_S = 600;

/** Why a login ended without a connection. A closed set: the surfaces map it to their own localized copy. */
export type XaiLoginFailure = 'startFailed' | 'expired' | 'denied' | 'timeout';

type LoginPhase = 'idle' | 'starting' | 'waiting';

interface LoginSession {
  userCode: string;
  verificationUrl: string;
}

interface UseXaiDeviceLoginOptions {
  onConnected: () => void;
  onFailed: (reason: XaiLoginFailure) => void;
}

export interface XaiDeviceLogin {
  phase: LoginPhase;
  /** The code the user types on the verification page; null outside the waiting phase. */
  userCode: string | null;
  /** Verification page with the code pre-filled when the server offers that; null outside the waiting phase. */
  verificationUrl: string | null;
  /**
   * Requests a device code and starts polling. Resolves to the verification URL so the caller can open it inside the
   * user gesture it handles, or to null when no login began (already running, or the request failed).
   */
  start: () => Promise<string | null>;
  /** Abandons the login in progress; nothing is reported afterwards. */
  cancel: () => void;
}

export function useXaiDeviceLogin({ onConnected, onFailed }: UseXaiDeviceLoginOptions): XaiDeviceLogin {
  const [phase, setPhase] = useState<LoginPhase>('idle');
  const [session, setSession] = useState<LoginSession | null>(null);

  // Bumped whenever a login is abandoned, so a response or timer of an older login can tell it is stale.
  const runRef = useRef(0);
  const busyRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const callbacksRef = useRef({ onConnected, onFailed });

  useEffect(() => {
    callbacksRef.current = { onConnected, onFailed };
  });

  const abandonRun = useCallback(() => {
    runRef.current += 1;
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const resetToIdle = useCallback(() => {
    busyRef.current = false;
    setPhase('idle');
    setSession(null);
  }, []);

  const cancel = useCallback(() => {
    abandonRun();
    resetToIdle();
  }, [abandonRun, resetToIdle]);

  useEffect(() => abandonRun, [abandonRun]);

  const start = useCallback(async (): Promise<string | null> => {
    if (busyRef.current) {
      return null;
    }
    busyRef.current = true;
    const run = ++runRef.current;
    const isCurrent = () => runRef.current === run;
    setPhase('starting');

    const fail = (reason: XaiLoginFailure) => {
      resetToIdle();
      callbacksRef.current.onFailed(reason);
    };

    let started: XaiOAuthStartResponse;
    try {
      started = await startXaiOAuth();
    } catch {
      if (isCurrent()) {
        fail('startFailed');
      }
      return null;
    }
    if (!isCurrent()) {
      return null;
    }
    if (!started.user_code || !started.verification_uri) {
      fail('startFailed');
      return null;
    }

    const verificationUrl = started.verification_uri_complete || started.verification_uri;
    setSession({ userCode: started.user_code, verificationUrl });
    setPhase('waiting');

    const deadline = Date.now() + (started.expires_in > 0 ? started.expires_in : DEFAULT_LIFETIME_S) * 1000;
    let intervalMs = Math.max((started.interval || DEFAULT_POLL_INTERVAL_S) * 1000, MIN_POLL_INTERVAL_MS);

    const poll = async () => {
      timerRef.current = null;
      if (!isCurrent()) {
        return;
      }
      if (Date.now() >= deadline) {
        fail('timeout');
        return;
      }

      let result: XaiOAuthPollResponse | null = null;
      try {
        result = await pollXaiOAuth(started.user_code);
      } catch {
        // A failed poll says nothing about the login; the next tick asks again until the code expires.
      }
      // A poll answered after the login was abandoned is ignored; the startup reconciliation realigns the stored flag.
      if (!isCurrent()) {
        return;
      }

      if (result?.status === 'success') {
        resetToIdle();
        connectProviderSubscription(XAI_PROVIDER_ID).catch((error: unknown) => {
          console.error('[useXaiDeviceLogin] Failed to apply the connected subscription:', error);
        });
        callbacksRef.current.onConnected();
        return;
      }
      if (result?.status === 'expired' || result?.status === 'denied') {
        fail(result.status);
        return;
      }
      if (result?.slow_down) {
        intervalMs += SLOW_DOWN_STEP_MS;
      }
      timerRef.current = setTimeout(poll, intervalMs);
    };
    timerRef.current = setTimeout(poll, intervalMs);

    return verificationUrl;
  }, [resetToIdle]);

  return {
    phase,
    userCode: session?.userCode ?? null,
    verificationUrl: session?.verificationUrl ?? null,
    start,
    cancel,
  };
}
