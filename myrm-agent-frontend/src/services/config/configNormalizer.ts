/**
 * Canonical config normalization — single pipeline for startup migration.
 * Stores hydrate from ConfigSyncManager; normalization runs here before commit.
 */

import type { ProviderConfig } from '@/store/config/providerTypes';
import { getInitialProviders } from '@/store/config/providerTypes';
import {
  deriveRoutingProfile,
  migratePersonalSettingsMedia,
  migrateProvidersBundle,
} from '@/store/config/providerIdentityMigration';
import type { ConfigKey, ConfigValueMap, PersonalSettingsConfigValue, ProvidersConfigValue } from './types';
import { DEFAULT_PERSONAL_SETTINGS } from './types';
import { valuesEqual } from './configFingerprint';

function mergeProviders(providers: ProviderConfig[]): ProviderConfig[] {
  if (!providers || !Array.isArray(providers)) {
    return getInitialProviders();
  }

  const initialProviders = getInitialProviders();
  const initialProviderMap = new Map(initialProviders.map((p) => [p.id, p]));
  const activeProviders = providers.filter((p) => !p.isBuiltIn || initialProviderMap.has(p.id));

  const mergedProviders = activeProviders.map((provider) => {
    const initialProvider = initialProviderMap.get(provider.id);
    if (initialProvider?.isBuiltIn) {
      return {
        ...initialProvider,
        isEnabled: provider.isEnabled,
        apiKeys: provider.apiKeys ?? initialProvider.apiKeys,
        apiUrl: provider.apiUrl ?? initialProvider.apiUrl,
        enabledModels: provider.enabledModels ?? initialProvider.enabledModels,
        availableModels: provider.availableModels ?? initialProvider.availableModels,
      };
    }
    return {
      ...provider,
      routingProfile: deriveRoutingProfile(provider),
    };
  });

  const providedIds = new Set(activeProviders.map((p) => p.id));
  const newBuiltInProviders = initialProviders.filter((p) => !providedIds.has(p.id));
  return [...mergedProviders, ...newBuiltInProviders];
}

export function normalizeProviders(raw: ProvidersConfigValue | null | undefined): ProvidersConfigValue {
  const migrated = migrateProvidersBundle(raw ?? { providers: [], defaultModelConfig: undefined, customModelInfo: {} });
  return {
    ...migrated,
    providers: mergeProviders(migrated.providers),
  };
}

export function normalizePersonalSettings(
  raw: PersonalSettingsConfigValue | null | undefined,
): PersonalSettingsConfigValue {
  const merged: PersonalSettingsConfigValue = {
    ...DEFAULT_PERSONAL_SETTINGS,
    ...raw,
  };
  return migratePersonalSettingsMedia(merged);
}

const NORMALIZERS: Partial<{
  [K in ConfigKey]: (raw: ConfigValueMap[K] | null | undefined) => ConfigValueMap[K];
}> = {
  providers: normalizeProviders as (raw: ProvidersConfigValue | null | undefined) => ProvidersConfigValue,
  personalSettings: normalizePersonalSettings as (
    raw: PersonalSettingsConfigValue | null | undefined,
  ) => PersonalSettingsConfigValue,
};

export function normalizeConfigValue<K extends ConfigKey>(
  key: K,
  raw: ConfigValueMap[K] | null | undefined,
): ConfigValueMap[K] | null {
  const normalizer = NORMALIZERS[key];
  if (!normalizer) {
    return raw ?? null;
  }
  return normalizer(raw) as ConfigValueMap[K];
}

export function isNormalizedDirty<K extends ConfigKey>(
  key: K,
  baseValue: ConfigValueMap[K] | null | undefined,
  rawValue: ConfigValueMap[K] | null | undefined,
): boolean {
  const normalized = normalizeConfigValue(key, rawValue);
  if (normalized === null) {
    return false;
  }
  return !valuesEqual(baseValue, normalized);
}

export const STARTUP_NORMALIZE_KEYS: readonly ConfigKey[] = ['providers', 'personalSettings'] as const;
