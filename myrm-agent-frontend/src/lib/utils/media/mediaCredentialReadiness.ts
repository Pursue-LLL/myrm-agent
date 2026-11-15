/**
 * [INPUT]
 * - imageModels::isImageModelSelected (POS: the image models the engine ships)
 * - ttsCatalog::isTtsSelected (POS: what counts as a chosen speech voice)
 * - mediaProviderStatus::resolveImageProviderId, videoProviderConfigId (POS: provider mapping)
 * - store/config/providerTypes::ProviderConfig (POS: WebUI provider rows)
 *
 * [OUTPUT]
 * - providerHasActiveApiKey
 * - MediaToolSetup, imageToolSetup, videoToolSetup, ttsToolSetup
 * - MediaCredentialWarningTool, MediaCredentialWarning, collectMediaCredentialWarnings
 *
 * [POS]
 * Client-side check of whether a media tool an Agent turns on would reach it: the user has chosen a model, and the
 * chosen provider has a key. The server mounts a media tool only for a model the user chose, so nothing is assumed
 * here either: no choice is `notSelected`, never a default that happens to have a key.
 */

import type { ProviderConfig } from '@/store/config/providerTypes';
import type { BuiltinToolId } from '@/store/chat/types';
import type { ImageGenerationConfig, VideoGenerationConfig, VoiceConfigValue } from '@/services/config/types';
import { isImageModelSelected } from './imageModels';
import { resolveImageProviderId, videoProviderConfigId, type MediaProviderStatus } from './mediaProviderStatus';
import { isTtsSelected } from './ttsCatalog';

function normalizeProviderSlug(providerId: string): string {
  return providerId.replace(/-/g, '_').toLowerCase();
}

export function providerHasActiveApiKey(providers: ProviderConfig[], providerId: string): boolean {
  const needle = normalizeProviderSlug(providerId);
  for (const row of providers) {
    if (!row.isEnabled) {
      continue;
    }
    const pid = normalizeProviderSlug(row.id);
    const routing = normalizeProviderSlug(row.routingProfile || '');
    if (pid !== needle && routing !== needle) {
      continue;
    }
    return row.apiKeys.some((entry) => entry.isActive && entry.key.trim().length > 0);
  }
  return false;
}

/** `notSelected`: nothing usable is chosen yet. `noCredential`: a choice is made but its provider has no key. */
export type MediaToolSetup = 'ready' | 'notSelected' | 'noCredential';

export function imageToolSetup(
  providers: ProviderConfig[],
  imageGeneration: ImageGenerationConfig | undefined,
): MediaToolSetup {
  const model = imageGeneration?.model;
  if (!isImageModelSelected(model)) {
    return 'notSelected';
  }
  return providerHasActiveApiKey(providers, resolveImageProviderId(model)) ? 'ready' : 'noCredential';
}

/** The provider must be one the server lists and serve the chosen model; before the list has loaded only the provider is known. */
function isVideoSelected(
  videoGeneration: VideoGenerationConfig | undefined,
  providerStatuses: Record<string, MediaProviderStatus>,
): videoGeneration is VideoGenerationConfig {
  const provider = videoGeneration?.provider;
  const model = videoGeneration?.model;
  if (!provider || !model) {
    return false;
  }
  const status = providerStatuses[provider];
  if (status) {
    return !status.models?.length || status.models.some((entry) => entry.id === model);
  }
  return Object.keys(providerStatuses).length === 0 && videoProviderConfigId(provider) !== undefined;
}

export function videoToolSetup(
  providers: ProviderConfig[],
  videoGeneration: VideoGenerationConfig | undefined,
  providerStatuses: Record<string, MediaProviderStatus>,
): MediaToolSetup {
  if (!isVideoSelected(videoGeneration, providerStatuses)) {
    return 'notSelected';
  }
  const { provider } = videoGeneration;
  if (providerStatuses[provider]?.hasApiKey) {
    return 'ready';
  }
  return providerHasActiveApiKey(providers, videoProviderConfigId(provider) ?? provider) ? 'ready' : 'noCredential';
}

export function ttsToolSetup(providers: ProviderConfig[], voice: VoiceConfigValue | null | undefined): MediaToolSetup {
  const provider = voice?.ttsProvider?.trim() ?? '';
  if (!isTtsSelected(provider, voice?.ttsModel, voice?.ttsVoice)) {
    return 'notSelected';
  }
  if (voice?.ttsApiKey?.trim()) {
    return 'ready';
  }
  return providerHasActiveApiKey(providers, provider) ? 'ready' : 'noCredential';
}

export type MediaCredentialWarningTool = Extract<BuiltinToolId, 'image_generation' | 'video_generation' | 'tts'>;

export interface MediaCredentialWarning {
  tool: MediaCredentialWarningTool;
  reason: Exclude<MediaToolSetup, 'ready'>;
}

/** One warning per enabled media tool that would not reach the Agent, saying whether a choice or a key is missing. */
export function collectMediaCredentialWarnings(
  enabledBuiltinTools: BuiltinToolId[],
  providers: ProviderConfig[],
  imageGeneration: ImageGenerationConfig | undefined,
  videoGeneration: VideoGenerationConfig | undefined,
  voice: VoiceConfigValue | null | undefined,
  providerStatuses: Record<string, MediaProviderStatus>,
): MediaCredentialWarning[] {
  const checks: Array<[MediaCredentialWarningTool, () => MediaToolSetup]> = [
    ['image_generation', () => imageToolSetup(providers, imageGeneration)],
    ['video_generation', () => videoToolSetup(providers, videoGeneration, providerStatuses)],
    ['tts', () => ttsToolSetup(providers, voice)],
  ];
  return checks.flatMap(([tool, setup]) => {
    if (!enabledBuiltinTools.includes(tool)) {
      return [];
    }
    const status = setup();
    return status === 'ready' ? [] : [{ tool, reason: status }];
  });
}
