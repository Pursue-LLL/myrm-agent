/**
 * [INPUT]
 * - TauriDesktopBridge / WebFallbackDesktopBridge
 * - React Context & Provider
 *
 * [OUTPUT]
 * - DesktopBridgeProvider: Context provider for desktop bridge
 * - useDesktopBridge: React hook accessing IDesktopBridge
 *
 * [POS]
 * React integration layer for DesktopBridge.
 */

'use client';

import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { isTauriEnvironment } from '@/lib/tauri';
import { TauriDesktopBridge } from './tauri-bridge';
import type { IDesktopBridge } from './types';
import { WebFallbackDesktopBridge } from './web-fallback-bridge';

const fallbackBridge = new WebFallbackDesktopBridge();
const DesktopBridgeContext = createContext<IDesktopBridge>(fallbackBridge);

export interface DesktopBridgeProviderProps {
  children: React.ReactNode;
  initialBridge?: IDesktopBridge;
}

export const DesktopBridgeProvider: React.FC<DesktopBridgeProviderProps> = ({ children, initialBridge }) => {
  const [bridge, setBridge] = useState<IDesktopBridge>(() => initialBridge || fallbackBridge);

  useEffect(() => {
    if (initialBridge) return;
    if (isTauriEnvironment()) {
      setBridge(new TauriDesktopBridge());
    } else {
      setBridge(fallbackBridge);
    }
  }, [initialBridge]);

  return <DesktopBridgeContext.Provider value={bridge}>{children}</DesktopBridgeContext.Provider>;
};

export function useDesktopBridge(): IDesktopBridge {
  return useContext(DesktopBridgeContext);
}
