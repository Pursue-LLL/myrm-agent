'use client';

import { useCallback } from 'react';
import useConfigStore from '@/store/useConfigStore';
import type { MCPServiceConfig } from '@/store/config/types';
import type { CatalogEntry } from './catalog-types';

export type CatalogConnectionState = 'available' | 'connected' | 'disabled';

/**
 * A catalog entry is connected once the user holds an MCP service under the name its template saves
 * (the identity the connect dialog guards duplicates with); `enabled === false` is a connected service
 * the user switched off.
 */
export function resolveCatalogConnectionState(
  entry: CatalogEntry,
  mcpConfigs: readonly MCPServiceConfig[],
): CatalogConnectionState {
  const serviceName = entry.mcpConfig?.name;
  if (typeof serviceName !== 'string') {
    return 'available';
  }
  const saved = mcpConfigs.find((config) => config.name === serviceName);
  if (!saved) {
    return 'available';
  }
  return saved.enabled === false ? 'disabled' : 'connected';
}

export function useCatalogConnectionState(): (entry: CatalogEntry) => CatalogConnectionState {
  const mcpConfigs = useConfigStore((state) => state.mcpConfigs);
  return useCallback((entry) => resolveCatalogConnectionState(entry, mcpConfigs), [mcpConfigs]);
}
