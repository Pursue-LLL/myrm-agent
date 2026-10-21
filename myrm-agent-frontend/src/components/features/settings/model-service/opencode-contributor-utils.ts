/** Detect OpenCode Go Muse Spark Contributor models (case-insensitive). */
export function isMuseSparkContributorModel(modelName: string): boolean {
  const normalized = modelName.trim().toLowerCase();
  return normalized.includes('muse-spark') && normalized.includes('contributor');
}

export interface OpenCodeModelSelectionLike {
  providerId: string;
  model: string;
}

/** Whether a bound model selection should show Contributor consent guidance. */
export function shouldShowContributorNotice(selection: OpenCodeModelSelectionLike | null | undefined): boolean {
  if (!selection) {
    return false;
  }
  return selection.providerId === 'opencode_go' && isMuseSparkContributorModel(selection.model);
}

/** Whether any slot selection should show Contributor consent guidance. */
export function anySelectionNeedsContributorNotice(
  selections: Array<OpenCodeModelSelectionLike | null | undefined>,
): boolean {
  return selections.some(shouldShowContributorNotice);
}

/** Whether any enabled model on the provider is a Contributor tier model. */
export function providerHasEnabledContributorModel(
  providerId: string,
  enabledModels: readonly string[] | undefined,
): boolean {
  if (providerId !== 'opencode_go') {
    return false;
  }
  return (enabledModels ?? []).some(isMuseSparkContributorModel);
}
