/**
 * [INPUT] channel preference, initial pairing options
 * [OUTPUT] useMobilePairingQrGateway hook managing QR lifecycle, countdown and companion connection
 * [POS] specialty-suites-gateway/useMobilePairingQrGateway.ts
 */

'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import type {
  ConnectorChannel,
  MobilePairingSession,
  CompanionSyncStatus,
  PairingStage,
} from './specialtyGatewayTypes';

export interface UseMobilePairingQrGatewayOptions {
  defaultChannel?: ConnectorChannel;
  expirySeconds?: number;
}

export function useMobilePairingQrGateway(options: UseMobilePairingQrGatewayOptions = {}) {
  const { defaultChannel = 'feishu', expirySeconds = 120 } = options;

  const [activeChannel, setActiveChannel] = useState<ConnectorChannel>(defaultChannel);
  const [session, setSession] = useState<MobilePairingSession | null>(null);
  const [companion, setCompanion] = useState<CompanionSyncStatus | null>(null);
  const [remainingSeconds, setRemainingSeconds] = useState<number>(expirySeconds);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const initiatePairing = useCallback(
    (channel: ConnectorChannel) => {
      setActiveChannel(channel);
      const newSessionId = `pair-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
      const dummyPublicKey = `ed25519-pub-${Math.random().toString(36).slice(2, 10)}`;
      const qrPayload = `myrm://pair?sid=${newSessionId}&ch=${channel}&key=${dummyPublicKey}&exp=${Date.now() + expirySeconds * 1000}`;

      const newSession: MobilePairingSession = {
        sessionId: newSessionId,
        channel,
        qrPayload,
        ephemeralPublicKey: dummyPublicKey,
        stage: 'waiting_scan',
        expiresAt: Date.now() + expirySeconds * 1000,
      };

      setSession(newSession);
      setRemainingSeconds(expirySeconds);
    },
    [expirySeconds],
  );

  const refreshQr = useCallback(() => {
    initiatePairing(activeChannel);
  }, [initiatePairing, activeChannel]);

  const disconnectCompanion = useCallback(() => {
    setCompanion(null);
    initiatePairing(activeChannel);
  }, [initiatePairing, activeChannel]);

  const simulateScanAndAuth = useCallback(
    (deviceLabel = 'iPhone 16 Pro (通勤助理)') => {
      if (!session) {
        return;
      }

      setSession((prev) => {
        if (!prev) {
          return null;
        }
        return {
          ...prev,
          stage: 'authenticated',
          deviceLabel,
        };
      });

      const newCompanion: CompanionSyncStatus = {
        pairedDeviceId: `dev-${Date.now().toString(36)}`,
        deviceType: 'ios',
        channel: session.channel,
        isOnline: true,
        queuedOfflineTasksCount: 0,
        lastSyncTimestamp: Date.now(),
      };
      setCompanion(newCompanion);
    },
    [session],
  );

  // Countdown timer effect
  useEffect(() => {
    if (!session || session.stage === 'authenticated' || session.stage === 'expired') {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }

    timerRef.current = setInterval(() => {
      setRemainingSeconds((prev) => {
        if (prev <= 1) {
          if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
          }
          setSession((cur) => {
            if (!cur || cur.stage === 'authenticated') {
              return cur;
            }
            return { ...cur, stage: 'expired' as PairingStage };
          });
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [session]);

  return {
    activeChannel,
    session,
    companion,
    remainingSeconds,
    initiatePairing,
    refreshQr,
    disconnectCompanion,
    simulateScanAndAuth,
  };
}
