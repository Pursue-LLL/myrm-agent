import type { ProviderConfig } from '@/store/config/providerTypes';
import type { BuiltinToolId } from '@/store/chat/types';
import type { ImageGenerationConfig, VideoGenerationConfig } from '@/services/config/types';
import type { VoiceConfigValue } from '@/services/config/types';
import {
  resolveImageProviderId,
  VIDEO_PROVIDER_CONFIG_IDS,
  type MediaProviderStatus,
} from '@/lib/utils/mediaProviderStatus';

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

export function isImageMediaCredentialReady(
  providers: ProviderConfig[],
  imageGeneration: ImageGenerationConfig | undefined,
): boolean {
  const model = imageGeneration?.model ?? 'dall-e-3';
  return providerHasActiveApiKey(providers, resolveImageProviderId(model));
}

export function isVideoMediaCredentialReady(
  providers: ProviderConfig[],
  videoGeneration: VideoGenerationConfig | undefined,
  providerStatuses: Record<string, MediaProviderStatus>,
): boolean {
  const provider = videoGeneration?.provider ?? 'openai';
  const status = providerStatuses[provider];
  if (status?.hasApiKey) {
    return true;
  }
  const configId = VIDEO_PROVIDER_CONFIG_IDS[provider] ?? provider;
  return providerHasActiveApiKey(providers, configId);
}

export function isTtsMediaCredentialReady(
  providers: ProviderConfig[],
  voice: VoiceConfigValue | null | undefined,
): boolean {
  const provider = voice?.ttsProvider?.trim() || 'openai';
  if (provider === 'edge') {
    return true;
  }
  if (voice?.ttsApiKey?.trim()) {
    return true;
  }
  return providerHasActiveApiKey(providers, provider);
}

export type MediaCredentialWarningTool = Extract<
  BuiltinToolId,
  'image_generation' | 'video_generation' | 'tts'
>;

export function collectMediaCredentialWarnings(
  enabledBuiltinTools: BuiltinToolId[],
  providers: ProviderConfig[],
  imageGeneration: ImageGenerationConfig | undefined,
  videoGeneration: VideoGenerationConfig | undefined,
  voice: VoiceConfigValue | null | undefined,
  providerStatuses: Record<string, MediaProviderStatus>,
): MediaCredentialWarningTool[] {
  const warnings: MediaCredentialWarningTool[] = [];

  if (enabledBuiltinTools.includes('image_generation') && !isImageMediaCredentialReady(providers, imageGeneration)) {
    warnings.push('image_generation');
  }
  if (enabledBuiltinTools.includes('video_generation') && !isVideoMediaCredentialReady(providers, videoGeneration, providerStatuses)) {
    warnings.push('video_generation');
  }
  if (enabledBuiltinTools.includes('tts') && !isTtsMediaCredentialReady(providers, voice)) {
    warnings.push('tts');
  }

  return warnings;
}
