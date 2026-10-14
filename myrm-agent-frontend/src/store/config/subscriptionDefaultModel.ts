/**
 * [INPUT]
 * @/services/models-dev::ModelsDevModel (POS: models.dev catalog entry shape)
 *
 * [OUTPUT]
 * pickSubscriptionDefaultModel
 *
 * [POS]
 * Chooses the model a freshly connected subscription provider starts with. It reads the live catalog instead of a
 * hard-coded id, so the choice follows the vendor's releases without a code change.
 */

import type { ModelsDevModel } from '@/services/models-dev';

/**
 * The legacy array form of `modalities` lists the inputs only, so it says nothing about the output; an entry that
 * omits the output list is given the benefit of the doubt.
 */
function outputsText(model: ModelsDevModel): boolean {
  const { modalities } = model;
  if (!modalities || Array.isArray(modalities) || !modalities.output) {
    return true;
  }
  return modalities.output.includes('text');
}

/** An agent drives its tools through the model, so only chat models with explicit tool calling qualify. */
function isAgentCapable(model: ModelsDevModel): boolean {
  return model.status !== 'deprecated' && model.tool_call === true && outputsText(model);
}

/** Code-unit order: ISO dates sort chronologically and the result never depends on the host locale. */
function compareText(a: string, b: string): number {
  if (a === b) {
    return 0;
  }
  return a < b ? -1 : 1;
}

/** Newest release first; entries without a date and equal dates fall back to the id so the pick is deterministic. */
function byNewestRelease(a: ModelsDevModel, b: ModelsDevModel): number {
  const dateOrder = compareText(b.release_date ?? '', a.release_date ?? '');
  return dateOrder !== 0 ? dateOrder : compareText(a.id, b.id);
}

/**
 * Returns the id of the newest tool-calling text model in the catalog, or null when the catalog offers none.
 */
export function pickSubscriptionDefaultModel(models: readonly ModelsDevModel[]): string | null {
  const [newest] = models.filter(isAgentCapable).sort(byNewestRelease);
  return newest?.id ?? null;
}
