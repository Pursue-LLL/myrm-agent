/**
 * [INPUT]
 * - (none — pure helpers)
 *
 * [OUTPUT]
 * - isFormalKoreanRepliesEnabled: read formal Korean policy from engine_params
 * - setFormalKoreanRepliesEnabled: toggle response_locale_policy on engine_params
 *
 * [POS]
 * Frontend mirror of harness response_locale SSOT. Agent Settings Switch reads/writes
 * engine_params.response_locale_policy for server converter suffix injection.
 */

/** Helpers for agent engine_params.response_locale_policy (formal Korean replies). */

type EngineParams = Record<string, unknown>;

interface ResponseLocalePolicy {
  locale: string;
  formality: 'formal-polite' | 'casual';
}

function parsePolicy(engineParams: EngineParams | null): ResponseLocalePolicy | null {
  if (!engineParams) {
    return null;
  }
  const raw = engineParams.response_locale_policy;
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  const record = raw as Record<string, unknown>;
  const locale = String(record.locale ?? '').trim();
  if (!locale) {
    return null;
  }
  const formalityRaw = String(record.formality ?? 'formal-polite')
    .trim()
    .toLowerCase();
  const formality: ResponseLocalePolicy['formality'] = formalityRaw === 'casual' ? 'casual' : 'formal-polite';
  return { locale, formality };
}

/** True when formal Korean (합니다体) output policy is enabled. */
export function isFormalKoreanRepliesEnabled(engineParams: EngineParams | null): boolean {
  const policy = parsePolicy(engineParams);
  if (!policy) {
    return false;
  }
  return policy.locale.toLowerCase().startsWith('ko') && policy.formality === 'formal-polite';
}

/** Toggle formal Korean policy on engine_params; returns null when empty. */
export function setFormalKoreanRepliesEnabled(
  engineParams: EngineParams | null,
  enabled: boolean,
): EngineParams | null {
  const next: EngineParams = { ...engineParams };
  if (enabled) {
    next.response_locale_policy = { locale: 'ko-KR', formality: 'formal-polite' };
  } else {
    delete next.response_locale_policy;
  }
  return Object.keys(next).length === 0 ? null : next;
}
