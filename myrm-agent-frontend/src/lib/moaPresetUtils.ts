/**
 * MoA preset helpers for chat model picker (session-level activation).
 *
 * [INPUT]
 * AgentConfig.engineParams.moa_overlay (profile preset definition)
 *
 * [OUTPUT]
 * isMoaPresetConfigured, countMoaReferenceModelsForPreset, listMoaPresetOptions,
 * resolveMoaPresetLabelKey, emptyMoaPresetsMap, buildPresetsForMoaEnable,
 * isActiveMoaPresetAvailable
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

type ModelSelection = { providerId: string; model: string };

function overlayBlock(
  engineParams: Record<string, unknown> | null | undefined,
): Record<string, unknown> | null {
  const overlay = engineParams?.moa_overlay;
  if (!overlay || typeof overlay !== 'object') {
    return null;
  }
  return overlay as Record<string, unknown>;
}

function topLevelReferenceSelections(overlay: Record<string, unknown>): ModelSelection[] {
  const refs = overlay.reference_model_selections;
  if (!Array.isArray(refs)) {
    return [];
  }
  return refs.filter(
    (item): item is ModelSelection =>
      typeof item === 'object' &&
      item !== null &&
      typeof (item as ModelSelection).providerId === 'string' &&
      typeof (item as ModelSelection).model === 'string',
  );
}

function presetBlocks(overlay: Record<string, unknown>): Partial<Record<MoaPresetId, Record<string, unknown>>> {
  const raw = overlay.presets;
  if (!raw || typeof raw !== 'object') {
    return {};
  }
  const blocks: Partial<Record<MoaPresetId, Record<string, unknown>>> = {};
  for (const presetId of MOA_PRESET_IDS) {
    const block = (raw as Record<string, unknown>)[presetId];
    if (block && typeof block === 'object') {
      blocks[presetId] = block as Record<string, unknown>;
    }
  }
  return blocks;
}

export function presetBlocksFromOverlay(
  overlay: Record<string, unknown>,
): Partial<Record<MoaPresetId, Record<string, unknown>>> {
  return presetBlocks(overlay);
}

function filterValidReferenceSelections(refs: unknown[]): ModelSelection[] {
  return refs.filter(
    (item): item is ModelSelection =>
      typeof item === 'object' &&
      item !== null &&
      typeof (item as ModelSelection).providerId === 'string' &&
      typeof (item as ModelSelection).model === 'string',
  );
}

export function resolvePresetReferenceSelections(
  overlay: Record<string, unknown>,
  presetId: MoaPresetId,
): ModelSelection[] {
  if ('presets' in overlay && overlay.presets && typeof overlay.presets === 'object') {
    const block = presetBlocks(overlay)[presetId];
    if (!block) {
      return [];
    }
    const refs = block.reference_model_selections;
    return Array.isArray(refs) ? filterValidReferenceSelections(refs) : [];
  }
  return topLevelReferenceSelections(overlay);
}

export function emptyMoaPresetsMap(): Record<MoaPresetId, { reference_model_selections: ModelSelection[] }> {
  return {
    [MOA_PRESET_DEFAULT_ID]: { reference_model_selections: [] },
    [MOA_PRESET_REVIEW_ID]: { reference_model_selections: [] },
    [MOA_PRESET_FAST_ID]: { reference_model_selections: [] },
  };
}

export function isMoaPresetConfigured(
  engineParams: Record<string, unknown> | null | undefined,
): boolean {
  const overlay = overlayBlock(engineParams);
  if (!overlay || !overlay.enabled) {
    return false;
  }
  const hasPresetRefs = MOA_PRESET_IDS.some(
    (presetId) => resolvePresetReferenceSelections(overlay, presetId).length > 0,
  );
  if ('presets' in overlay && overlay.presets && typeof overlay.presets === 'object') {
    return hasPresetRefs;
  }
  return hasPresetRefs || topLevelReferenceSelections(overlay).length > 0;
}

export function countMoaReferenceModelsForPreset(
  engineParams: Record<string, unknown> | null | undefined,
  presetId: MoaPresetId,
): number {
  const overlay = overlayBlock(engineParams);
  if (!overlay) {
    return 0;
  }
  return resolvePresetReferenceSelections(overlay, presetId).length;
}

/** @deprecated Use countMoaReferenceModelsForPreset — kept for call-site compatibility */
export function countMoaReferenceModels(
  engineParams: Record<string, unknown> | null | undefined,
): number {
  return countMoaReferenceModelsForPreset(engineParams, MOA_PRESET_DEFAULT_ID);
}

export interface MoaPresetOption {
  id: MoaPresetId;
  labelKey: 'defaultLabel' | 'reviewLabel' | 'fastLabel';
  refCount: number;
}

const PRESET_LABEL_KEYS: Record<MoaPresetId, MoaPresetOption['labelKey']> = {
  [MOA_PRESET_DEFAULT_ID]: 'defaultLabel',
  [MOA_PRESET_REVIEW_ID]: 'reviewLabel',
  [MOA_PRESET_FAST_ID]: 'fastLabel',
};

export function resolveMoaPresetLabelKey(
  presetId: string | null | undefined,
): MoaPresetOption['labelKey'] | null {
  if (!presetId || !(MOA_PRESET_IDS as readonly string[]).includes(presetId)) {
    return null;
  }
  return PRESET_LABEL_KEYS[presetId as MoaPresetId];
}

export function listMoaPresetOptions(
  engineParams: Record<string, unknown> | null | undefined,
): MoaPresetOption[] {
  return MOA_PRESET_IDS.map((presetId) => ({
    id: presetId,
    labelKey: PRESET_LABEL_KEYS[presetId],
    refCount: countMoaReferenceModelsForPreset(engineParams, presetId),
  })).filter((option) => option.refCount > 0);
}

export function isActiveMoaPresetAvailable(
  engineParams: Record<string, unknown> | null | undefined,
  presetId: string | null,
): boolean {
  if (!presetId) {
    return true;
  }
  return listMoaPresetOptions(engineParams).some((option) => option.id === presetId);
}

/** Persist top-level legacy refs into presets.default when enabling MoA overlay. */
export function buildPresetsForMoaEnable(
  overlay: Record<string, unknown>,
): Record<MoaPresetId, { reference_model_selections: ModelSelection[] }> {
  const overlayWithPresets: Record<string, unknown> = {
    ...overlay,
    presets: overlay.presets ?? emptyMoaPresetsMap(),
  };
  const merged = emptyMoaPresetsMap();
  for (const presetId of MOA_PRESET_IDS) {
    const block = presetBlocks(overlayWithPresets)[presetId];
    merged[presetId] = {
      ...(block ?? {}),
      reference_model_selections: resolvePresetReferenceSelections(overlayWithPresets, presetId),
    };
  }
  const topRefs = topLevelReferenceSelections(overlay);
  if (topRefs.length > 0 && merged[MOA_PRESET_DEFAULT_ID].reference_model_selections.length === 0) {
    merged[MOA_PRESET_DEFAULT_ID] = {
      ...merged[MOA_PRESET_DEFAULT_ID],
      reference_model_selections: topRefs,
    };
  }
  return merged;
}
