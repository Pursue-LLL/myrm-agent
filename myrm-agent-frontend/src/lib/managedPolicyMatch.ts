/** Case-sensitive glob match aligned with harness fnmatch.fnmatchcase semantics. */

export function fnmatchCase(pattern: string, slug: string): boolean {
  const trimmedPattern = pattern.trim();
  const trimmedSlug = slug.trim();
  if (!trimmedPattern || !trimmedSlug) {
    return false;
  }
  const escaped = trimmedPattern.replace(/[.+^${}()|[\]\\]/g, '\\$&');
  const regexSource = `^${escaped.replace(/\*/g, '.*').replace(/\?/g, '.')}$`;
  return new RegExp(regexSource).test(trimmedSlug);
}

export function matchesAnyModelPattern(patterns: string[], modelSlug: string): boolean {
  if (!modelSlug.trim() || patterns.length === 0) {
    return false;
  }
  return patterns.some((pattern) => fnmatchCase(pattern, modelSlug));
}

export interface ManagedPolicyEffective {
  active?: boolean;
  ignoreAllowlistForModels?: string[];
  forceAutoReviewForModels?: string[];
  disableYolo?: boolean;
  disableAllowAlways?: boolean;
}

export function managedPolicyConstraintsForModel(
  policy: ManagedPolicyEffective,
  modelSlug: string | null | undefined,
): {
  forceAutoReview: boolean;
  ignoreAllowlist: boolean;
} {
  const slug = modelSlug?.trim() ?? '';
  return {
    forceAutoReview: matchesAnyModelPattern(policy.forceAutoReviewForModels ?? [], slug),
    ignoreAllowlist: matchesAnyModelPattern(policy.ignoreAllowlistForModels ?? [], slug),
  };
}

/** True when org MAP blocks YOLO fast path for this model (mirrors harness map_suppresses_yolo). */
export function mapSuppressesYoloForModel(
  policy: ManagedPolicyEffective,
  modelSlug: string | null | undefined,
): boolean {
  const constraints = managedPolicyConstraintsForModel(policy, modelSlug);
  return constraints.forceAutoReview || constraints.ignoreAllowlist;
}

/** True when org MAP blocks YOLO (global disable or per-model suppress). */
export function orgBlocksYoloForModel(policy: ManagedPolicyEffective, modelSlug: string | null | undefined): boolean {
  if (policy.disableYolo) {
    return true;
  }
  return mapSuppressesYoloForModel(policy, modelSlug);
}
