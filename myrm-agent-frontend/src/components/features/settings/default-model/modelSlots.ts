import type { DefaultModelConfig, SingleModelSelection } from '@/store/config/providerTypes';
import useProviderStore from '@/store/useProviderStore';

type ProviderState = ReturnType<typeof useProviderStore.getState>;
export type SelectionWriter = (selection: SingleModelSelection | null) => void;

interface ModelSlotBinding {
  /** The slot's saved selection; `undefined` when an optional slot was never saved. */
  read: (config: DefaultModelConfig) => SingleModelSelection | null | undefined;
  /** The store action that persists a selection for the slot. */
  write: (state: ProviderState) => SelectionWriter;
}

/** Every model slot of the default-model page, bound to its config field and to the store action that writes it. */
export const MODEL_SLOTS = {
  base: { read: (c) => c.baseModel.primary, write: (s) => s.setBaseModel },
  baseFallback: { read: (c) => c.baseModel.fallback, write: (s) => s.setBaseModelFallback },
  lite: { read: (c) => c.liteModel.primary, write: (s) => s.setLiteModel },
  liteFallback: { read: (c) => c.liteModel.fallback, write: (s) => s.setLiteModelFallback },
  routingLight: { read: (c) => c.routingConfig?.lightModel?.primary, write: (s) => s.setRoutingLightModel },
  routingLightFallback: {
    read: (c) => c.routingConfig?.lightModel?.fallback,
    write: (s) => s.setRoutingLightModelFallback,
  },
  routingReasoning: { read: (c) => c.routingConfig?.reasoningModel?.primary, write: (s) => s.setRoutingReasoningModel },
  routingReasoningFallback: {
    read: (c) => c.routingConfig?.reasoningModel?.fallback,
    write: (s) => s.setRoutingReasoningModelFallback,
  },
  vision: { read: (c) => c.visionFallbackModel?.primary, write: (s) => s.setVisionFallbackModel },
  visionFallback: { read: (c) => c.visionFallbackModel?.fallback, write: (s) => s.setVisionFallbackModelFallback },
  video: { read: (c) => c.videoFallbackModel?.primary, write: (s) => s.setVideoFallbackModel },
  videoFallback: { read: (c) => c.videoFallbackModel?.fallback, write: (s) => s.setVideoFallbackModelFallback },
  code: { read: (c) => c.codeModel?.primary, write: (s) => s.setCodeModel },
  codeFallback: { read: (c) => c.codeModel?.fallback, write: (s) => s.setCodeModelFallback },
  longDoc: { read: (c) => c.longDocModel?.primary, write: (s) => s.setLongDocModel },
  longDocFallback: { read: (c) => c.longDocModel?.fallback, write: (s) => s.setLongDocModelFallback },
  backgroundEvolution: {
    read: (c) => c.backgroundEvolutionModel?.primary,
    write: (s) => s.setBackgroundEvolutionModel,
  },
  backgroundEvolutionFallback: {
    read: (c) => c.backgroundEvolutionModel?.fallback,
    write: (s) => s.setBackgroundEvolutionModelFallback,
  },
} as const satisfies Record<string, ModelSlotBinding>;

export type ModelSlotId = keyof typeof MODEL_SLOTS;

/** The slot's current selection and the action that replaces it. */
export function useModelSlot(slot: ModelSlotId): readonly [SingleModelSelection | null, SelectionWriter] {
  const selection = useProviderStore((state) => MODEL_SLOTS[slot].read(state.defaultModelConfig) ?? null);
  const select = useProviderStore((state) => MODEL_SLOTS[slot].write(state));
  return [selection, select];
}
