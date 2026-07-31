import type { CustomModelInfo, DefaultModelConfig, SingleModelSelection } from './providerTypes';

type ModelInfoLookup = (providerId: string, model: string) => CustomModelInfo | undefined;

export type EnabledVisionModelEntry = {
  providerId: string;
  providerName: string;
  model: string;
};

function selectionSupportsVision(
  selection: SingleModelSelection | null | undefined,
  getModelInfo: ModelInfoLookup,
): boolean {
  if (!selection) return false;
  return getModelInfo(selection.providerId, selection.model)?.supports_vision ?? false;
}

/** Whether the configured model stack can handle images via native vision or vision fallback chain. */
export function hasConfiguredVisionCapability(
  defaultModelConfig: DefaultModelConfig | undefined,
  getModelInfo: ModelInfoLookup,
): boolean {
  if (!defaultModelConfig) return false;

  const visionSlot = defaultModelConfig.visionFallbackModel;
  if (selectionSupportsVision(visionSlot?.primary, getModelInfo)) return true;
  if (selectionSupportsVision(visionSlot?.fallback, getModelInfo)) return true;
  return selectionSupportsVision(defaultModelConfig.baseModel?.primary, getModelInfo);
}

/** First enabled model with vision support, in provider list order. Skips optional exclude selection. */
export function findRecommendedVisionFallbackSelection(
  enabledModels: EnabledVisionModelEntry[],
  getModelInfo: ModelInfoLookup,
  exclude?: SingleModelSelection | null,
): SingleModelSelection | null {
  for (const entry of enabledModels) {
    if (
      exclude &&
      exclude.providerId === entry.providerId &&
      exclude.model === entry.model
    ) {
      continue;
    }
    if (getModelInfo(entry.providerId, entry.model)?.supports_vision) {
      return { providerId: entry.providerId, model: entry.model };
    }
  }
  return null;
}

/** Whether to show the one-click vision fallback recommendation control. */
export function shouldOfferVisionFallbackRecommendation(
  defaultModelConfig: DefaultModelConfig | undefined,
  getModelInfo: ModelInfoLookup,
): boolean {
  if (!defaultModelConfig) return false;
  if (defaultModelConfig.visionFallbackModel?.primary) return false;
  return !selectionSupportsVision(defaultModelConfig.baseModel?.primary, getModelInfo);
}

/** Whether video uploads need vision fallback because the base model lacks video input. */
export function hasVisionFallbackForVideo(
  defaultModelConfig: DefaultModelConfig | undefined,
  getModelInfo: ModelInfoLookup,
): boolean {
  if (!defaultModelConfig) return false;

  const visionSlot = defaultModelConfig.visionFallbackModel;
  return (
    selectionSupportsVision(visionSlot?.primary, getModelInfo) ||
    selectionSupportsVision(visionSlot?.fallback, getModelInfo)
  );
}
