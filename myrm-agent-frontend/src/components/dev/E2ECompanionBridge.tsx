'use client';

/**
 * [INPUT]
 * - @/store/useCompanionStore (POS: pet palette + doctor expand pending)
 * - @/store/useFeatureGateStore (POS: companion_mode feature gate)
 *
 * [OUTPUT]
 * - E2ECompanionBridge: localhost dev-only `window.__MYRM_E2E_COMPANION__` for CDP Chrome E2E
 *
 * [POS]
 * App shell dev bridge for companion health-check UI signoff (non-terminal-user feature).
 */
import { useLayoutEffect } from 'react';

import useCompanionStore from '@/store/useCompanionStore';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';

function isLocalDevHost(): boolean {
  if (typeof window === 'undefined') {return false;}
  const host = window.location.hostname;
  return host === '127.0.0.1' || host === 'localhost';
}

function enableCompanionModeForE2e(): void {
  const gate = useFeatureGateStore.getState();
  const next = new Set(gate.enabledFeatures);
  next.add('companion_mode');
  useFeatureGateStore.setState({ enabledFeatures: next, initialized: true });
}

export default function E2ECompanionBridge() {
  useLayoutEffect(() => {
    if (!isLocalDevHost()) {return;}

    window.__MYRM_E2E_COMPANION__ = {
      enableCompanionModeForE2e,
      prepareBrokenSpriteForE2e: () => {
        enableCompanionModeForE2e();
        useCompanionStore.setState({
          spriteEnabled: true,
          spriteConfig: {
            petSlug: 'e2e-missing-sprite-pet',
            contentSha256: '0'.repeat(64),
          },
        });
      },
      openHealthCheck: () => {
        enableCompanionModeForE2e();
        useCompanionStore.getState().openCompanionHealthCheck();
      },
      getHealthCheckState: () => {
        const companion = useCompanionStore.getState();
        return {
          petPaletteOpen: companion.petPaletteOpen,
          doctorExpandPending: companion.doctorExpandPending,
          companionModeEnabled: useFeatureGateStore.getState().isEnabled('companion_mode'),
        };
      },
      closePetPaletteForE2e: () => {
        useCompanionStore.setState({ petPaletteOpen: false, doctorExpandPending: false });
      },
    };

    return () => {
      delete window.__MYRM_E2E_COMPANION__;
    };
  }, []);

  return null;
}
