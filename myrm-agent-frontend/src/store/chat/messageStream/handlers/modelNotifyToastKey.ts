/**
 * [INPUT]
 * - locales progressSteps.model_failover_* / model_escalated_* / model_recovery_* (POS: 6-locale model notify toast SSOT)
 *
 * [OUTPUT]
 * - resolveModelFailoverToastKey(): full i18n key for showI18nToast
 * - resolveModelFailoverProgressStepKey(): progressSteps step_key for UI
 * - MODEL_ESCALATED_* / MODEL_RECOVERY_*: SSOT keys for MODEL_ESCALATED / MODEL_RECOVERY SSE paths
 *
 * [POS]
 * i18n key SSOT for modelNotifyEvents (MODEL_ESCALATED / MODEL_FAILOVER / MODEL_RECOVERY).
 * FailoverReason string → progressSteps key mapping shared by STATUS and MODEL_FAILOVER SSE paths.
 */

export const MODEL_ESCALATED_TOAST_KEY = 'progressSteps.model_escalated';
export const MODEL_ESCALATED_REASON_KEY = 'progressSteps.model_escalated_reason';
export const MODEL_RECOVERY_TOAST_KEY = 'progressSteps.model_recovery';
export const MODEL_RECOVERY_DOWNTIME_KEY = 'progressSteps.model_recovery_downtime';

const FAILOVER_REASON_TO_PROGRESS_KEY: Record<string, string> = {
  rate_limit: 'progressSteps.model_failover_rate_limit',
  overloaded: 'progressSteps.model_failover_overloaded',
  timeout: 'progressSteps.model_failover_timeout',
  billing: 'progressSteps.model_failover_billing',
  context_overflow: 'progressSteps.model_failover_context_overflow',
  response_format: 'progressSteps.model_failover_response_format_error',
  format: 'progressSteps.model_failover_response_format_error',
  model_not_found: 'progressSteps.model_failover_model_not_found',
  auth_permanent: 'progressSteps.model_failover_auth',
  session_expired: 'progressSteps.model_failover_auth',
  safety_block: 'progressSteps.safety_fallback_active',
};

export function resolveModelFailoverToastKey(reason?: string): string {
  if (!reason) {
    return 'progressSteps.model_failover';
  }
  return FAILOVER_REASON_TO_PROGRESS_KEY[reason] ?? 'progressSteps.model_failover';
}

export function resolveModelFailoverProgressStepKey(reason?: string): string {
  const toastKey = resolveModelFailoverToastKey(reason);
  return toastKey.replace(/^progressSteps\./, '');
}
