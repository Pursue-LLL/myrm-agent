/**
 * [INPUT]
 * - locale-manifest deferred settings sections list
 *
 * [OUTPUT]
 * React context: deferred locale bundle merged into ClientIntlProvider
 *
 * [POS]
 * Settings routes block first paint until deferred settings i18n is loaded.
 */
'use client';

import { createContext, useContext } from 'react';

interface DeferredLocaleContextValue {
  deferredLocaleReady: boolean;
}

const DeferredLocaleContext = createContext<DeferredLocaleContextValue>({
  deferredLocaleReady: false,
});

export function DeferredLocaleProvider({
  deferredLocaleReady,
  children,
}: {
  deferredLocaleReady: boolean;
  children: React.ReactNode;
}) {
  return (
    <DeferredLocaleContext.Provider value={{ deferredLocaleReady }}>{children}</DeferredLocaleContext.Provider>
  );
}

export function useDeferredLocaleReady(): boolean {
  return useContext(DeferredLocaleContext).deferredLocaleReady;
}
