'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  resolveThemeMarketplaceGateState,
  type ThemeMarketplaceGateState,
} from '@/lib/theme-marketplace-gate';

export function useThemeMarketplaceGate(): {
  gate: ThemeMarketplaceGateState;
  refresh: () => void;
} {
  const [gate, setGate] = useState<ThemeMarketplaceGateState>('loading');

  const refresh = useCallback(() => {
    setGate('loading');
    void resolveThemeMarketplaceGateState()
      .then((next) => {
        setGate(next);
      })
      .catch(() => {
        setGate('offline');
      });
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === 'auth_token') {
        refresh();
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [refresh]);

  return { gate, refresh };
}
