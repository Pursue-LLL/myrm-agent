/**
 * MoA preset helpers for chat model picker (session-level activation).
 *
 * [INPUT]
 * AgentConfig.engineParams.moa_overlay (profile preset definition)
 *
 * [OUTPUT]
 * isMoaPresetConfigured, countMoaReferenceModels, listMoaPresetOptions
 *
 * [POS]
 * Frontend guard for showing the virtual Mixture of Agents picker group.
 */

export const MOA_PRESET_DEFAULT_ID = 'default';
export const MOA_PRESET_REVIEW_ID = 'review';
export const MOA_PRESET_FAST_ID = 'fast';

export const MOA_PRESET_IDS = [
  MOA_PRESET_DEFAULT_ID,
  MOA_PRESET_REVIEW_ID,
  MOA_PRESET_FAST_ID,
] as const;

export type MoaPresetId = (typeof MOA_PRESET_IDS)[number];

export function isMoaPresetConfigured(
  engineParams: Record<string, unknown> | null | undefined,
): boolean {
  const overlay = engineParams?.moa_overlay;
  if (!overlay || typeof overlay !== 'object') {
    return false;
  }
  const block = overlay as Record<string, unknown>;
  if (!block.enabled) {
    return false;
  }
  const refs = block.reference_model_selections;
  return Array.isArray(refs) && refs.length > 0;
}

export function countMoaReferenceModels(
  engineParams: Record<string, unknown> | null | undefined,
): number {
  const overlay = engineParams?.moa_overlay;
  if (!overlay || typeof overlay !== 'object') {
    return 0;
  }
  const refs = (overlay as Record<string, unknown>).reference_model_selections;
  return Array.isArray(refs) ? refs.length : 0;
}

export interface MoaPresetOption {
  id: MoaPresetId;
  labelKey: 'defaultLabel' | 'reviewLabel' | 'fastLabel';
  refCount: number;
}

export function listMoaPresetOptions(
  engineParams: Record<string, unknown> | null | undefined,
): MoaPresetOption[] {
  const refCount = countMoaReferenceModels(engineParams);
  return [
    { id: MOA_PRESET_DEFAULT_ID, labelKey: 'defaultLabel', refCount },
    { id: MOA_PRESET_REVIEW_ID, labelKey: 'reviewLabel', refCount },
    { id: MOA_PRESET_FAST_ID, labelKey: 'fastLabel', refCount },
  ];
}
