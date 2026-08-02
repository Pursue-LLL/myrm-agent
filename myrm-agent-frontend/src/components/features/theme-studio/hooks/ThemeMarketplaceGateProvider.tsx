'use client';

/**
 * [INPUT]
 * - lib/theme-marketplace-gate::resolveThemeMarketplaceGateState (POS: CP health + JWT gate SSOT)
 *
 * [OUTPUT]
 * - ThemeMarketplaceGateProvider, useThemeMarketplaceGate
 *
 * [POS]
 * Single shared gate probe for Theme Studio marketplace panels (Gallery/Creator/Admin).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  resolveThemeMarketplaceGateState,
  type ThemeMarketplaceGateState,
} from '@/lib/theme-marketplace-gate';

type ThemeMarketplaceGateContextValue = {
  gate: ThemeMarketplaceGateState;
  refresh: () => void;
};

const ThemeMarketplaceGateContext = createContext<ThemeMarketplaceGateContextValue | null>(null);

export function ThemeMarketplaceGateProvider({ children }: { children: ReactNode }) {
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
    const onFocus = () => {
      refresh();
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
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

  const value = useMemo(() => ({ gate, refresh }), [gate, refresh]);

  return (
    <ThemeMarketplaceGateContext.Provider value={value}>{children}</ThemeMarketplaceGateContext.Provider>
  );
}

export function useThemeMarketplaceGate(): ThemeMarketplaceGateContextValue {
  const context = useContext(ThemeMarketplaceGateContext);
  if (!context) {
    throw new Error('useThemeMarketplaceGate must be used within ThemeMarketplaceGateProvider');
  }
  return context;
}
