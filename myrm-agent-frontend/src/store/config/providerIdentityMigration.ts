/**
 * One-shot migration for unified provider identity (storage id ↔ LiteLLM routing).
 *
 * Rewrites persisted Provider bundle + personal media settings once on load/import.
 * No runtime alias tables on the server — selections must resolve to concrete rows.
 */

import type {
  CustomModelInfo,
  DefaultModelConfig,
  ModelSlot,
  ProviderConfig,
  RoutingConfig,
  SingleModelSelection,
} from './providerTypes';
import { CUSTOM_PROVIDER_TYPE_INFO, getInitialDefaultModelConfig, PROVIDER_TO_LITELLM_PREFIX } from './providerTypes';
import type { ProvidersConfigValue } from '@/services/config/types';
import type { PersonalSettingsConfigValue, VideoGenerationConfig } from '@/services/config/types';

import legacyRemapJson from './provider_legacy_remap.json';

/** Canonical remap — byte-synced with `provider_legacy_remap.json` beside `providers.py`. */
const LEGACY_PROVIDER_ID_REMAP: Readonly<Record<string, string>> = legacyRemapJson as Record<string, string>;

export function remapLegacyProviderId(providerId: string): string {
  if (!providerId) return providerId;
  const slug = providerId.replace(/-/g, '_');
  return LEGACY_PROVIDER_ID_REMAP[slug] ?? LEGACY_PROVIDER_ID_REMAP[providerId] ?? providerId;
}

export function deriveRoutingProfile(provider: ProviderConfig): string {
  if (provider.routingProfile && provider.routingProfile.length > 0) {
    return provider.routingProfile;
  }
  if (provider.providerType) {
    return CUSTOM_PROVIDER_TYPE_INFO[provider.providerType].litellmPrefix;
  }
  return PROVIDER_TO_LITELLM_PREFIX[provider.id] ?? provider.id;
}

function migrateSelection(sel: SingleModelSelection | null): SingleModelSelection | null {
  if (!sel) return null;
  const nextId = remapLegacyProviderId(sel.providerId);
  return nextId === sel.providerId ? sel : { ...sel, providerId: nextId };
}

function migrateModelSlot(slot: ModelSlot): ModelSlot {
  return {
    ...slot,
    primary: migrateSelection(slot.primary),
    fallback: migrateSelection(slot.fallback),
  };
}

function migrateRouting(cfg: RoutingConfig | null): RoutingConfig | null {
  if (!cfg) return null;
  return {
    enabled: cfg.enabled,
    lightModel: migrateModelSlot(cfg.lightModel),
    reasoningModel: migrateModelSlot(cfg.reasoningModel),
  };
}

export function migrateDefaultModelConfig(config: DefaultModelConfig): DefaultModelConfig {
  return {
    ...config,
    baseModel: migrateModelSlot(config.baseModel),
    liteModel: migrateModelSlot(config.liteModel),
    fastModeModel: config.fastModeModel ? migrateModelSlot(config.fastModeModel) : null,
    routingConfig: migrateRouting(config.routingConfig),
    visionFallbackModel: migrateSelection(config.visionFallbackModel ?? null),
  };
}

function migrateProviders(providers: readonly ProviderConfig[]): ProviderConfig[] {
  return providers.map((raw) => {
    const base = raw as ProviderConfig;
    const nextId = remapLegacyProviderId(base.id);
    const routingProfile = deriveRoutingProfile({ ...base, id: nextId });
    return { ...base, id: nextId, routingProfile };
  });
}

function migrateCustomModelInfo(info: Record<string, CustomModelInfo>): Record<string, CustomModelInfo> {
  const next: Record<string, CustomModelInfo> = {};
  for (const [key, meta] of Object.entries(info)) {
    const slash = key.indexOf('/');
    if (slash <= 0) {
      next[key] = meta;
      continue;
    }
    const pid = key.slice(0, slash);
    const rest = key.slice(slash);
    const mappedPid = remapLegacyProviderId(pid);
    next[`${mappedPid}${rest}`] = meta;
  }
  return next;
}

function migrateVideoGeneration(cfg: VideoGenerationConfig | undefined): VideoGenerationConfig | undefined {
  if (!cfg) return cfg;
  const mapPid = (s: string) => {
    const slug = s.replace(/-/g, '_');
    if (slug === 'google') return 'gemini';
    return remapLegacyProviderId(s);
  };
  const provider = mapPid(cfg.provider) as VideoGenerationConfig['provider'];
  const fallbackProviders = (cfg.fallbackProviders ?? []).map((fb) => ({
    ...fb,
    provider: mapPid(String(fb.provider)),
  }));
  return { ...cfg, provider, fallbackProviders };
}

/** Migrate persisted providers bundle (SQLite / Postgres / export JSON). */
export function migrateProvidersBundle(input: {
  providers?: readonly ProviderConfig[];
  defaultModelConfig?: DefaultModelConfig;
  customModelInfo?: Record<string, CustomModelInfo>;
}): ProvidersConfigValue {
  const mergedDefault: DefaultModelConfig = {
    ...getInitialDefaultModelConfig(),
    ...input.defaultModelConfig,
  };
  return {
    providers: migrateProviders(input.providers ?? []),
    defaultModelConfig: migrateDefaultModelConfig(mergedDefault),
    customModelInfo: migrateCustomModelInfo(input.customModelInfo ?? {}),
  };
}

/** Migrate media-related fields inside personal settings (video provider enums). */
export function migratePersonalSettingsMedia(settings: PersonalSettingsConfigValue): PersonalSettingsConfigValue {
  const videoGeneration = migrateVideoGeneration(settings.videoGeneration);
  return {
    ...settings,
    ...(videoGeneration !== undefined ? { videoGeneration } : {}),
  };
}
